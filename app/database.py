import json
import re
import zlib
from datetime import date, timedelta
from typing import Optional

import asyncpg

from app.config import Settings

_AVATAR_COLORS = ["#4F8EF7", "#A855F7", "#22c55e", "#eab308", "#ef4444", "#06b6d4", "#f97316"]

# Slugs end up in Redis channel names and Qdrant collection names, and ":" is
# the separator inside a dialog key — keep them boring.
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")

SERVICE_COLORS = ["#4F8EF7", "#A855F7", "#22c55e", "#f97316", "#ec4899", "#06b6d4", "#eab308", "#ef4444"]

# Dialogs always travel with their service so the API and the WebSocket router
# never have to look it up separately.
_DIALOG_SELECT = """
    SELECT d.*, s.slug AS service_slug, s.name AS service_name, s.color AS service_color
    FROM dialogs d JOIN services s ON s.id = d.service_id
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def avatar_color(dialog_id: str) -> str:
    # crc32 rather than hash(): Python salts string hashing per process, which
    # would give the same user a different colour after every restart.
    return _AVATAR_COLORS[zlib.crc32(dialog_id.encode()) % len(_AVATAR_COLORS)]


def make_dialog_key(slug: str, external_id) -> str:
    """Internal primary key of a dialog. n8n only ever sees external_id."""
    return f"{slug}:{external_id}"


def make_initials(name: str) -> str:
    if not name:
        return "??"
    parts = name.split()
    return "".join(p[0] for p in parts[:2]).upper()


# ── Manager ───────────────────────────────────────────────────────────────────

class DatabaseManager:

    def __init__(self, settings: Settings):
        self.settings = settings
        self.pool: asyncpg.Pool = None

    async def init_db(self):
        s = self.settings
        self.pool = await asyncpg.create_pool(
            host=s.POSTGRES_HOST,
            port=s.POSTGRES_PORT,
            database=s.POSTGRES_DB,
            user=s.POSTGRES_USER,
            password=s.POSTGRES_PASSWORD,
        )
        async with self.pool.acquire() as conn:
            await self._migrate(conn)
        print("Database initialized")

    async def _migrate(self, conn):
        # If old n8n-style tables exist (no dialog_id TEXT column) — rename them
        # to *_legacy so we don't conflict but keep the data accessible.
        old_dialogs = await conn.fetchval(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='dialogs'"
        )
        has_dialog_id = await conn.fetchval(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='dialogs' AND column_name='dialog_id'"
        ) if old_dialogs else 0

        if old_dialogs and not has_dialog_id:
            for t in ("chat_topics", "messages", "dialogs"):
                exists = await conn.fetchval(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name=$1", t
                )
                if exists:
                    await conn.execute(f"ALTER TABLE {t} RENAME TO {t}_legacy")

        # ── Core tables ───────────────────────────────────────────────────────
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS dialogs (
                dialog_id           TEXT PRIMARY KEY,
                chat_id             TEXT NOT NULL,
                status              TEXT NOT NULL DEFAULT 'new',
                ai_enabled          BOOLEAN NOT NULL DEFAULT TRUE,
                operator_called     BOOLEAN NOT NULL DEFAULT FALSE,
                unread_count        INTEGER NOT NULL DEFAULT 0,
                user_name           TEXT,
                user_username       TEXT,
                user_plan           TEXT DEFAULT 'Basic',
                user_sub_status     TEXT DEFAULT 'active',
                user_next_payment   TEXT,
                user_traffic_used   FLOAT DEFAULT 0,
                user_traffic_total  FLOAT DEFAULT 100,
                last_payment_amount TEXT,
                last_payment_date   TEXT,
                last_message_text   TEXT,
                last_message_time   TIMESTAMPTZ DEFAULT NOW(),
                created_at          TIMESTAMPTZ DEFAULT NOW(),
                updated_at          TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id            SERIAL PRIMARY KEY,
                dialog_id     TEXT NOT NULL REFERENCES dialogs(dialog_id) ON DELETE CASCADE,
                kind          TEXT NOT NULL,
                text          TEXT,
                file_id       TEXT,
                file_type     TEXT,
                file_url      TEXT,
                operator_name TEXT,
                created_at    TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS messages_dialog_idx ON messages (dialog_id, created_at)"
        )
        await conn.execute(
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS category TEXT"
        )
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS operators (
                id         SERIAL PRIMARY KEY,
                name       TEXT NOT NULL,
                tg         TEXT,
                tg_id      BIGINT,
                role       TEXT NOT NULL DEFAULT 'agent',
                online     BOOLEAN DEFAULT FALSE,
                initials   TEXT,
                color      TEXT DEFAULT '#4F8EF7',
                notif_prefs TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS kb_articles (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL,
                category   TEXT NOT NULL,
                keywords   TEXT NOT NULL,
                content    TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # ── n8n shared tables ────────────────────────────────────────────────
        # n8n connects to the same PostgreSQL and uses these tables.
        # Names are prefixed with n8n_ to avoid collisions with helpdesk tables.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS n8n_dialogs (
                id         BIGSERIAL PRIMARY KEY,
                user_id    BIGINT NOT NULL,
                username   TEXT,
                ai_status  BOOLEAN NOT NULL DEFAULT TRUE,
                status     TEXT NOT NULL DEFAULT 'new',
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS n8n_dialogs_user_idx ON n8n_dialogs (user_id)"
        )
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS n8n_messages (
                id         BIGSERIAL PRIMARY KEY,
                user_id    BIGINT NOT NULL,
                dialog_id  BIGINT NOT NULL REFERENCES n8n_dialogs(id) ON DELETE CASCADE,
                message    TEXT,
                type       TEXT NOT NULL DEFAULT 'user',
                file_id    TEXT,
                file_type  TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS n8n_messages_dialog_idx ON n8n_messages (dialog_id)"
        )

        # ── Forward migrations ────────────────────────────────────────────────
        # Add new columns without dropping anything; safe to re-run on every
        # startup because ADD COLUMN IF NOT EXISTS is idempotent.
        new_cols = [
            # dialogs
            ("dialogs", "chat_id",             "TEXT"),
            ("dialogs", "operator_called",      "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("dialogs", "unread_count",         "INTEGER NOT NULL DEFAULT 0"),
            ("dialogs", "user_name",            "TEXT"),
            ("dialogs", "user_username",        "TEXT"),
            ("dialogs", "user_plan",            "TEXT DEFAULT 'Basic'"),
            ("dialogs", "user_sub_status",      "TEXT DEFAULT 'active'"),
            ("dialogs", "user_next_payment",    "TEXT"),
            ("dialogs", "user_traffic_used",    "FLOAT DEFAULT 0"),
            ("dialogs", "user_traffic_total",   "FLOAT DEFAULT 100"),
            ("dialogs", "last_payment_amount",  "TEXT"),
            ("dialogs", "last_payment_date",    "TEXT"),
            ("dialogs", "last_message_text",    "TEXT"),
            ("dialogs", "last_message_time",    "TIMESTAMPTZ DEFAULT NOW()"),
            ("dialogs", "updated_at",           "TIMESTAMPTZ DEFAULT NOW()"),
            ("dialogs", "summary",              "TEXT"),
            # messages
            ("messages", "kind",          "TEXT"),
            ("messages", "text",          "TEXT"),
            ("messages", "file_id",       "TEXT"),
            ("messages", "file_type",     "TEXT"),
            ("messages", "file_url",      "TEXT"),
            ("messages", "operator_name", "TEXT"),
            # operators
            ("operators", "tg",            "TEXT"),
            ("operators", "tg_id",         "BIGINT"),
            ("operators", "online",        "BOOLEAN DEFAULT FALSE"),
            ("operators", "initials",      "TEXT"),
            ("operators", "color",         "TEXT DEFAULT '#4F8EF7'"),
            ("operators", "notif_prefs",   "TEXT"),
            ("operators", "password_hash", "TEXT"),
        ]
        for table, col, typedef in new_cols:
            await conn.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {typedef}"
            )

        await self._migrate_services(conn)

    # ── Services migration ────────────────────────────────────────────────────

    async def _already_applied(self, conn, migration_id: str) -> bool:
        return bool(await conn.fetchval(
            "SELECT COUNT(*) FROM schema_migrations WHERE id = $1", migration_id
        ))

    async def _mark_applied(self, conn, migration_id: str):
        await conn.execute(
            "INSERT INTO schema_migrations (id) VALUES ($1) ON CONFLICT DO NOTHING",
            migration_id,
        )

    async def _migrate_services(self, conn):
        """Introduce the service (VPN brand) dimension.

        Unlike the ADD COLUMN block above this needs one-shot data migrations
        (rewriting primary keys), so they are gated on schema_migrations.
        """
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id         TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id         SERIAL PRIMARY KEY,
                slug       TEXT UNIQUE NOT NULL,
                name       TEXT NOT NULL,
                color      TEXT NOT NULL DEFAULT '#4F8EF7',
                is_default BOOLEAN NOT NULL DEFAULT FALSE,
                is_active  BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS operator_services (
                operator_id INTEGER NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
                service_id  INTEGER NOT NULL REFERENCES services(id)  ON DELETE CASCADE,
                PRIMARY KEY (operator_id, service_id)
            )
        """)
        # Separate table rather than a column on `settings`: that table's PK is
        # `key`, and ADD COLUMN IF NOT EXISTS cannot widen a primary key.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS service_settings (
                service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
                key        TEXT NOT NULL,
                value      TEXT NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (service_id, key)
            )
        """)

        # ── Default service ───────────────────────────────────────────────────
        default_id = await conn.fetchval(
            "SELECT id FROM services WHERE is_default ORDER BY id LIMIT 1"
        )
        if default_id is None:
            slug = self.settings.DEFAULT_SERVICE_SLUG
            if not SLUG_RE.match(slug):
                raise ValueError(
                    f"DEFAULT_SERVICE_SLUG={slug!r} must match {SLUG_RE.pattern}"
                )
            default_id = await conn.fetchval(
                """INSERT INTO services (slug, name, color, is_default)
                   VALUES ($1, $2, $3, TRUE)
                   ON CONFLICT (slug) DO UPDATE SET is_default = TRUE
                   RETURNING id""",
                slug, self.settings.DEFAULT_SERVICE_NAME, SERVICE_COLORS[0],
            )
            print(f"Default service: {slug} (id={default_id})")

        # ── Attach existing rows to the default service ───────────────────────
        await conn.execute("ALTER TABLE dialogs ADD COLUMN IF NOT EXISTS service_id INTEGER")
        await conn.execute("ALTER TABLE dialogs ADD COLUMN IF NOT EXISTS external_id TEXT")
        await conn.execute("ALTER TABLE kb_articles ADD COLUMN IF NOT EXISTS service_id INTEGER")
        await conn.execute(
            "UPDATE dialogs SET service_id = $1, external_id = COALESCE(external_id, dialog_id) "
            "WHERE service_id IS NULL",
            default_id,
        )
        await conn.execute(
            "UPDATE kb_articles SET service_id = $1 WHERE service_id IS NULL", default_id
        )

        # ── One-shot: re-key dialogs to {slug}:{external_id} ──────────────────
        # n8n dialog ids are per-database sequences; with more than one n8n
        # instance the same id can arrive from two brands and silently merge
        # their conversations.
        if not await self._already_applied(conn, "001_composite_dialog_keys"):
            async with conn.transaction():
                fkeys = await conn.fetch(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = 'messages'::regclass AND contype = 'f'"
                )
                for fk in fkeys:
                    await conn.execute(
                        f'ALTER TABLE messages DROP CONSTRAINT "{fk["conname"]}"'
                    )
                # messages first, while dialogs still holds the old keys
                await conn.execute("""
                    UPDATE messages m SET dialog_id = s.slug || ':' || m.dialog_id
                    FROM dialogs d JOIN services s ON s.id = d.service_id
                    WHERE d.dialog_id = m.dialog_id AND m.dialog_id NOT LIKE '%:%'
                """)
                await conn.execute("""
                    UPDATE dialogs d SET dialog_id = s.slug || ':' || d.external_id
                    FROM services s
                    WHERE s.id = d.service_id AND d.dialog_id NOT LIKE '%:%'
                """)
                await conn.execute("""
                    ALTER TABLE messages ADD CONSTRAINT messages_dialog_id_fkey
                    FOREIGN KEY (dialog_id) REFERENCES dialogs(dialog_id)
                    ON DELETE CASCADE ON UPDATE CASCADE
                """)
                await self._mark_applied(conn, "001_composite_dialog_keys")
            print("Migration 001_composite_dialog_keys applied")

        # ── One-shot: move global ai_settings/schedule onto the default service
        if not await self._already_applied(conn, "002_service_settings"):
            await conn.execute(
                """INSERT INTO service_settings (service_id, key, value)
                   SELECT $1, key, value FROM settings WHERE key IN ('ai_settings', 'schedule')
                   ON CONFLICT DO NOTHING""",
                default_id,
            )
            await self._mark_applied(conn, "002_service_settings")

        # ── One-shot: grant every existing operator the default service ───────
        if not await self._already_applied(conn, "003_operator_default_service"):
            await conn.execute(
                """INSERT INTO operator_services (operator_id, service_id)
                   SELECT id, $1 FROM operators ON CONFLICT DO NOTHING""",
                default_id,
            )
            await self._mark_applied(conn, "003_operator_default_service")

        # ── Constraints and indexes ───────────────────────────────────────────
        await conn.execute("ALTER TABLE dialogs ALTER COLUMN service_id SET NOT NULL")
        await conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS dialogs_service_external_idx "
            "ON dialogs (service_id, external_id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS dialogs_service_updated_idx "
            "ON dialogs (service_id, updated_at DESC)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS dialogs_service_status_idx "
            "ON dialogs (service_id, status)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS kb_articles_service_idx ON kb_articles (service_id)"
        )

    # ── Services ──────────────────────────────────────────────────────────────

    async def get_services(self) -> list[dict]:
        rows = await self.pool.fetch("SELECT * FROM services ORDER BY id")
        return [dict(r) for r in rows]

    async def get_service(self, service_id: int) -> Optional[dict]:
        row = await self.pool.fetchrow("SELECT * FROM services WHERE id = $1", service_id)
        return dict(row) if row else None

    async def get_service_by_slug(self, slug: str) -> Optional[dict]:
        row = await self.pool.fetchrow("SELECT * FROM services WHERE slug = $1", slug)
        return dict(row) if row else None

    async def get_default_service(self) -> Optional[dict]:
        row = await self.pool.fetchrow(
            "SELECT * FROM services WHERE is_default ORDER BY id LIMIT 1"
        )
        return dict(row) if row else None

    async def create_service(self, slug: str, name: str, color: str = None) -> dict:
        if color is None:
            count = await self.pool.fetchval("SELECT COUNT(*) FROM services")
            color = SERVICE_COLORS[count % len(SERVICE_COLORS)]
        row = await self.pool.fetchrow(
            "INSERT INTO services (slug, name, color) VALUES ($1,$2,$3) RETURNING *",
            slug, name, color,
        )
        return dict(row)

    async def update_service(self, service_id: int, name: str, color: str, is_active: bool) -> Optional[dict]:
        row = await self.pool.fetchrow(
            "UPDATE services SET name=$1, color=$2, is_active=$3 WHERE id=$4 RETURNING *",
            name, color, is_active, service_id,
        )
        return dict(row) if row else None

    async def delete_service(self, service_id: int) -> bool:
        result = await self.pool.execute("DELETE FROM services WHERE id=$1", service_id)
        return result == "DELETE 1"

    async def count_service_dialogs(self, service_id: int) -> int:
        return await self.pool.fetchval(
            "SELECT COUNT(*) FROM dialogs WHERE service_id=$1", service_id
        ) or 0

    async def get_service_counters(self) -> dict[int, dict]:
        """Per-service dialog counters, keyed by service_id.

        `badge` is what the UI shows next to the service name: anything that
        still needs attention — a brand-new dialog or one with unread messages.
        """
        rows = await self.pool.fetch("""
            SELECT service_id,
                   COUNT(*) FILTER (WHERE status <> 'closed') AS open_count,
                   COUNT(*) FILTER (WHERE status <> 'closed'
                                      AND (status = 'new' OR unread_count > 0)) AS badge_count
            FROM dialogs GROUP BY service_id
        """)
        return {
            r["service_id"]: {"open": int(r["open_count"]), "badge": int(r["badge_count"])}
            for r in rows
        }

    # ── Operator ↔ service access ─────────────────────────────────────────────

    async def get_operator_service_ids(self, op_id: int) -> list[int]:
        rows = await self.pool.fetch(
            "SELECT service_id FROM operator_services WHERE operator_id=$1 ORDER BY service_id",
            op_id,
        )
        return [r["service_id"] for r in rows]

    async def get_service_ids_by_operator(self) -> dict[int, list[int]]:
        """All access flags at once — avoids N+1 when listing operators."""
        rows = await self.pool.fetch(
            "SELECT operator_id, service_id FROM operator_services ORDER BY service_id"
        )
        out: dict[int, list[int]] = {}
        for r in rows:
            out.setdefault(r["operator_id"], []).append(r["service_id"])
        return out

    async def set_operator_services(self, op_id: int, service_ids: list[int]):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM operator_services WHERE operator_id=$1", op_id
                )
                if service_ids:
                    await conn.executemany(
                        "INSERT INTO operator_services (operator_id, service_id) "
                        "VALUES ($1,$2) ON CONFLICT DO NOTHING",
                        [(op_id, sid) for sid in service_ids],
                    )

    # ── Per-service settings ──────────────────────────────────────────────────

    async def get_service_setting_json(self, service_id: int, key: str, default=None):
        val = await self.pool.fetchval(
            "SELECT value FROM service_settings WHERE service_id=$1 AND key=$2",
            service_id, key,
        )
        return json.loads(val) if val else default

    async def set_service_setting_json(self, service_id: int, key: str, value):
        await self.pool.execute(
            "INSERT INTO service_settings (service_id, key, value) VALUES ($1,$2,$3) "
            "ON CONFLICT (service_id, key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()",
            service_id, key, json.dumps(value, ensure_ascii=False),
        )

    # ── Dialogs ───────────────────────────────────────────────────────────────

    async def upsert_dialog(
        self, dialog_id: str, chat_id: str, service_id: int, external_id: str,
        ai_enabled: bool = True, user_info: dict = None,
    ) -> dict:
        ui = user_info or {}
        row = await self.pool.fetchrow(
            """
            INSERT INTO dialogs (
                dialog_id, chat_id, service_id, external_id, ai_enabled,
                user_name, user_username, user_plan, user_sub_status,
                user_next_payment, user_traffic_used, user_traffic_total,
                last_payment_amount, last_payment_date, unread_count
            ) VALUES ($1,$2,$13,$14,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12, 1)
            ON CONFLICT (dialog_id) DO UPDATE SET
                ai_enabled          = EXCLUDED.ai_enabled,
                user_name           = COALESCE(EXCLUDED.user_name,          dialogs.user_name),
                user_username       = COALESCE(EXCLUDED.user_username,      dialogs.user_username),
                user_plan           = COALESCE(EXCLUDED.user_plan,          dialogs.user_plan),
                user_sub_status     = COALESCE(EXCLUDED.user_sub_status,    dialogs.user_sub_status),
                user_next_payment   = COALESCE(EXCLUDED.user_next_payment,  dialogs.user_next_payment),
                user_traffic_used   = COALESCE(EXCLUDED.user_traffic_used,  dialogs.user_traffic_used),
                user_traffic_total  = COALESCE(EXCLUDED.user_traffic_total, dialogs.user_traffic_total),
                last_payment_amount = COALESCE(EXCLUDED.last_payment_amount,dialogs.last_payment_amount),
                last_payment_date   = COALESCE(EXCLUDED.last_payment_date,  dialogs.last_payment_date),
                unread_count        = dialogs.unread_count + 1,
                updated_at          = NOW()
            RETURNING *, (xmax = 0) AS is_new_dialog
            """,
            dialog_id, chat_id, ai_enabled,
            ui.get("user_name"), ui.get("user_username"),
            ui.get("user_plan", "Basic"), ui.get("user_sub_status", "active"),
            ui.get("user_next_payment"),
            float(ui.get("user_traffic_used") or 0),
            float(ui.get("user_traffic_total") or 100),
            ui.get("user_last_payment_amount"), ui.get("user_last_payment_date"),
            service_id, str(external_id),
        )
        return dict(row)

    async def get_dialogs_for(self, service_ids: list[int]) -> list[dict]:
        """Dialogs of the given services, newest first. Empty list → no access."""
        if not service_ids:
            return []
        rows = await self.pool.fetch(
            _DIALOG_SELECT + " WHERE d.service_id = ANY($1::int[]) ORDER BY d.updated_at DESC",
            service_ids,
        )
        return [dict(r) for r in rows]

    async def get_dialog(self, dialog_id: str) -> Optional[dict]:
        row = await self.pool.fetchrow(
            _DIALOG_SELECT + " WHERE d.dialog_id = $1", dialog_id
        )
        return dict(row) if row else None

    async def get_dialog_history(
        self, chat_id: str, service_id: int, exclude_dialog_id: str = "",
    ) -> list[dict]:
        # Scoped to the service: the same Telegram chat_id can talk to several
        # brands, and one brand's operators must not see another's history.
        rows = await self.pool.fetch(
            """SELECT dialog_id, last_message_text, summary, status, updated_at
               FROM dialogs
               WHERE chat_id=$1 AND service_id=$2 AND status='closed' AND dialog_id!=$3
               ORDER BY updated_at DESC LIMIT 10""",
            chat_id, service_id, exclude_dialog_id,
        )
        return [dict(r) for r in rows]

    async def update_last_message(self, dialog_id: str, text: str):
        await self.pool.execute(
            "UPDATE dialogs SET last_message_text=$1, last_message_time=NOW(), updated_at=NOW() WHERE dialog_id=$2",
            text, dialog_id,
        )

    async def update_status(self, dialog_id: str, status: str):
        await self.pool.execute(
            "UPDATE dialogs SET status=$1, updated_at=NOW() WHERE dialog_id=$2",
            status, dialog_id,
        )

    async def update_ai_enabled(self, dialog_id: str, ai_enabled: bool):
        await self.pool.execute(
            "UPDATE dialogs SET ai_enabled=$1, updated_at=NOW() WHERE dialog_id=$2",
            ai_enabled, dialog_id,
        )

    async def update_operator_called(self, dialog_id: str, called: bool):
        await self.pool.execute(
            "UPDATE dialogs SET operator_called=$1, updated_at=NOW() WHERE dialog_id=$2",
            called, dialog_id,
        )

    async def clear_unread(self, dialog_id: str):
        await self.pool.execute(
            "UPDATE dialogs SET unread_count=0 WHERE dialog_id=$1", dialog_id
        )

    # ── Messages ──────────────────────────────────────────────────────────────

    async def save_message(
        self, dialog_id: str, kind: str, text: str = None,
        file_id: str = None, file_type: str = None,
        file_url: str = None, operator_name: str = None,
    ) -> dict:
        row = await self.pool.fetchrow(
            """INSERT INTO messages (dialog_id, kind, text, file_id, file_type, file_url, operator_name)
               VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING *""",
            dialog_id, kind, text, file_id, file_type, file_url, operator_name,
        )
        return dict(row)

    async def get_messages(self, dialog_id: str) -> list[dict]:
        rows = await self.pool.fetch(
            "SELECT * FROM messages WHERE dialog_id=$1 ORDER BY created_at ASC", dialog_id,
        )
        return [dict(r) for r in rows]

    async def save_dialog_summary(self, dialog_id: str, summary: str):
        await self.pool.execute(
            "UPDATE dialogs SET summary=$1 WHERE dialog_id=$2", summary, dialog_id,
        )

    async def get_messages_for_summary(self, dialog_id: str) -> list[dict]:
        rows = await self.pool.fetch(
            """SELECT kind, text FROM messages
               WHERE dialog_id=$1 AND kind IN ('user','ai','operator') AND text IS NOT NULL AND text != ''
               ORDER BY created_at ASC LIMIT 40""",
            dialog_id,
        )
        return [dict(r) for r in rows]

    async def update_message_category(self, msg_id: int, category: str):
        await self.pool.execute(
            "UPDATE messages SET category=$1 WHERE id=$2", category, msg_id,
        )

    # ── Operators ─────────────────────────────────────────────────────────────

    async def get_operators(self) -> list[dict]:
        rows = await self.pool.fetch("SELECT * FROM operators ORDER BY id")
        return [dict(r) for r in rows]

    async def get_operator(self, op_id: int) -> Optional[dict]:
        row = await self.pool.fetchrow("SELECT * FROM operators WHERE id=$1", op_id)
        return dict(row) if row else None

    async def get_operator_by_tg(self, tg: str) -> Optional[dict]:
        row = await self.pool.fetchrow("SELECT * FROM operators WHERE tg=$1", tg)
        return dict(row) if row else None

    async def set_password(self, op_id: int, password_hash: str):
        await self.pool.execute(
            "UPDATE operators SET password_hash=$1 WHERE id=$2", password_hash, op_id
        )

    async def create_operator(self, name: str, tg: str, role: str, tg_id: int = None) -> dict:
        initials = make_initials(name)
        colors = ["#A855F7", "#4F8EF7", "#22c55e", "#eab308", "#f97316", "#ef4444", "#06b6d4"]
        count = await self.pool.fetchval("SELECT COUNT(*) FROM operators")
        color = colors[count % len(colors)]
        row = await self.pool.fetchrow(
            "INSERT INTO operators (name, tg, tg_id, role, initials, color) VALUES ($1,$2,$3,$4,$5,$6) RETURNING *",
            name, tg, tg_id, role, initials, color,
        )
        return dict(row)

    async def update_operator(self, op_id: int, name: str, tg: str, role: str, tg_id: int = None) -> Optional[dict]:
        initials = make_initials(name)
        row = await self.pool.fetchrow(
            "UPDATE operators SET name=$1, tg=$2, tg_id=$3, role=$4, initials=$5 WHERE id=$6 RETURNING *",
            name, tg, tg_id, role, initials, op_id,
        )
        return dict(row) if row else None

    async def delete_operator(self, op_id: int) -> bool:
        result = await self.pool.execute("DELETE FROM operators WHERE id=$1", op_id)
        return result == "DELETE 1"

    async def set_operator_online(self, op_id: int, online: bool):
        await self.pool.execute("UPDATE operators SET online=$1 WHERE id=$2", online, op_id)

    async def update_operator_notif_prefs(self, op_id: int, prefs: dict):
        await self.pool.execute(
            "UPDATE operators SET notif_prefs=$1 WHERE id=$2",
            json.dumps(prefs, ensure_ascii=False), op_id,
        )

    # ── Settings ──────────────────────────────────────────────────────────────

    async def get_setting(self, key: str) -> Optional[str]:
        row = await self.pool.fetchrow("SELECT value FROM settings WHERE key=$1", key)
        return row["value"] if row else None

    async def set_setting(self, key: str, value: str):
        await self.pool.execute(
            "INSERT INTO settings (key,value) VALUES ($1,$2) "
            "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()",
            key, value,
        )

    async def get_setting_json(self, key: str, default=None):
        val = await self.get_setting(key)
        return json.loads(val) if val else default

    async def set_setting_json(self, key: str, value):
        await self.set_setting(key, json.dumps(value, ensure_ascii=False))

    # ── Stats ─────────────────────────────────────────────────────────────────

    async def get_stats(self, days: int = 14, service_ids: list[int] = None) -> dict:
        # `svc` narrows every query to the services the caller may see; passing
        # None (admin, no filter chosen) keeps the old global behaviour.
        svc = "AND service_id = ANY($1::int[])" if service_ids is not None else ""
        args = [service_ids] if service_ids is not None else []

        today_total = await self.pool.fetchval(
            f"SELECT COUNT(*) FROM dialogs WHERE created_at::date = CURRENT_DATE {svc}", *args
        ) or 0
        today_closed = await self.pool.fetchval(
            "SELECT COUNT(*) FROM dialogs WHERE status='closed' "
            f"AND updated_at::date = CURRENT_DATE {svc}", *args
        ) or 0
        ai_resolved = await self.pool.fetchval(
            "SELECT COUNT(*) FROM dialogs WHERE status='closed' AND operator_called=FALSE "
            f"AND updated_at::date = CURRENT_DATE {svc}", *args
        ) or 0
        ai_pct = int(ai_resolved / today_closed * 100) if today_closed else 0

        # Daily counts for last N days (missing days filled with 0)
        daily_svc = "AND service_id = ANY($2::int[])" if service_ids is not None else ""
        daily_rows = await self.pool.fetch(
            f"""SELECT created_at::date as d, COUNT(*) as cnt
                FROM dialogs WHERE created_at >= NOW() - ($1 || ' days')::interval {daily_svc}
                GROUP BY d ORDER BY d""",
            str(days), *args,
        )
        daily_map = {str(r["d"]): r["cnt"] for r in daily_rows}
        today = date.today()
        daily = [
            int(daily_map.get(str(today - timedelta(days=days - 1 - i)), 0))
            for i in range(days)
        ]

        # Hourly distribution over the last 14 days
        hourly_rows = await self.pool.fetch(
            f"""SELECT EXTRACT(HOUR FROM created_at)::int as h, COUNT(*) as cnt
                FROM dialogs WHERE created_at >= NOW() - '14 days'::interval {svc}
                GROUP BY h ORDER BY h""",
            *args,
        )
        hourly_map = {r["h"]: r["cnt"] for r in hourly_rows}
        hourly = [int(hourly_map.get(h, 0)) for h in range(24)]

        # Operator performance — attributed via the operator who wrote the last
        # reply in the dialog. Previously every operator got the same global
        # count, which made the column meaningless.
        closed_svc = "AND d.service_id = ANY($1::int[])" if service_ids is not None else ""
        closed_rows = await self.pool.fetch(
            f"""SELECT m.operator_name AS name, COUNT(DISTINCT d.dialog_id) AS cnt
                FROM dialogs d JOIN messages m ON m.dialog_id = d.dialog_id
                WHERE d.status='closed' AND d.updated_at::date = CURRENT_DATE
                  AND m.kind='operator' AND m.operator_name IS NOT NULL {closed_svc}
                GROUP BY m.operator_name""",
            *args,
        )
        closed_by_name = {r["name"]: int(r["cnt"]) for r in closed_rows}

        op_rows = await self.pool.fetch("SELECT * FROM operators ORDER BY id")
        operators = [
            {
                "id": op["id"], "name": op["name"], "tg": op["tg"],
                "role": op["role"], "online": op["online"],
                "initials": op["initials"], "color": op["color"],
                "closed": closed_by_name.get(op["name"], 0), "avgTime": "—",
            }
            for op in op_rows
        ]

        return {
            "today_total": today_total,
            "today_closed": today_closed,
            "ai_pct": ai_pct,
            "daily": daily,
            "hourly": hourly,
            "operators": operators,
            "top_questions": await self._get_top_questions(service_ids),
        }

    async def _get_top_questions(self, service_ids: list[int] = None) -> list[dict]:
        svc = "AND d.service_id = ANY($1::int[])" if service_ids is not None else ""
        args = [service_ids] if service_ids is not None else []
        rows = await self.pool.fetch(
            f"""SELECT m.category AS q, COUNT(*) AS count
                FROM messages m JOIN dialogs d ON d.dialog_id = m.dialog_id
                WHERE m.kind='user' AND m.category IS NOT NULL
                  AND m.created_at >= NOW() - '30 days'::interval {svc}
                GROUP BY m.category ORDER BY count DESC LIMIT 10""",
            *args,
        )
        return [{"q": r["q"], "count": r["count"]} for r in rows]

    # ── Knowledge Base ────────────────────────────────────────────────────────

    async def save_kb_article(
        self, id: str, title: str, category: str, keywords: str, content: str, service_id: int,
    ):
        await self.pool.execute(
            """INSERT INTO kb_articles (id, title, category, keywords, content, service_id)
               VALUES ($1,$2,$3,$4,$5,$6)
               ON CONFLICT (id) DO UPDATE SET
                 title=EXCLUDED.title, category=EXCLUDED.category,
                 keywords=EXCLUDED.keywords, content=EXCLUDED.content,
                 service_id=EXCLUDED.service_id""",
            id, title, category, keywords, content, service_id,
        )

    async def get_kb_articles(self, service_id: int) -> list[dict]:
        rows = await self.pool.fetch(
            "SELECT * FROM kb_articles WHERE service_id=$1 ORDER BY created_at DESC",
            service_id,
        )
        return [dict(r) for r in rows]

    async def get_kb_article(self, article_id: str) -> Optional[dict]:
        row = await self.pool.fetchrow("SELECT * FROM kb_articles WHERE id=$1", article_id)
        return dict(row) if row else None

    async def delete_kb_article(self, article_id: str) -> bool:
        result = await self.pool.execute("DELETE FROM kb_articles WHERE id=$1", article_id)
        return result == "DELETE 1"

    async def close(self):
        if self.pool:
            await self.pool.close()
