import json
from datetime import date, timedelta
from typing import Optional

import asyncpg

from app.config import Settings

_AVATAR_COLORS = ["#4F8EF7", "#A855F7", "#22c55e", "#eab308", "#ef4444", "#06b6d4", "#f97316"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def avatar_color(dialog_id: str) -> str:
    return _AVATAR_COLORS[hash(dialog_id) % len(_AVATAR_COLORS)]


def make_initials(name: str) -> str:
    if not name:
        return "??"
    parts = name.split()
    return "".join(p[0] for p in parts[:2]).upper()


# ── Manager ───────────────────────────────────────────────────────────────────

class DatabaseManager:
    _ASSIGN_LOCK = 7_777_777  # pg advisory lock key — serializes all assignment operations

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
        await conn.execute(
            "ALTER TABLE dialogs ADD COLUMN IF NOT EXISTS user_notes TEXT"
        )
        await conn.execute(
            "ALTER TABLE dialogs ADD COLUMN IF NOT EXISTS user_photo_url TEXT"
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

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS message_templates (
                id         SERIAL PRIMARY KEY,
                group_name TEXT NOT NULL DEFAULT 'Общие',
                title      TEXT NOT NULL,
                text       TEXT NOT NULL,
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
            ("dialogs", "rating",               "SMALLINT"),
            ("dialogs", "closed_at",            "TIMESTAMPTZ"),
            ("dialogs", "assigned_operator",    "TEXT"),
            ("dialogs", "waiting_reason",       "TEXT"),
            ("dialogs", "sla_seconds_total",    "INTEGER NOT NULL DEFAULT 0"),
            ("dialogs", "sla_started_at",       "TIMESTAMPTZ"),
            ("dialogs", "queued_at",            "TIMESTAMPTZ"),
            ("dialogs", "return_requested_at",  "TIMESTAMPTZ"),
            # messages
            ("messages", "kind",            "TEXT"),
            ("messages", "text",            "TEXT"),
            ("messages", "file_id",         "TEXT"),
            ("messages", "file_type",       "TEXT"),
            ("messages", "file_url",        "TEXT"),
            ("messages", "operator_name",   "TEXT"),
            ("messages", "delivery_status", "TEXT DEFAULT 'pending'"),
            ("messages", "delivery_error",  "TEXT"),
            # operators
            ("operators", "tg",            "TEXT"),
            ("operators", "tg_id",         "BIGINT"),
            ("operators", "online",        "BOOLEAN DEFAULT FALSE"),
            ("operators", "paused",        "BOOLEAN DEFAULT FALSE"),
            ("operators", "initials",      "TEXT"),
            ("operators", "color",         "TEXT DEFAULT '#4F8EF7'"),
            ("operators", "notif_prefs",   "TEXT"),
            ("operators", "password_hash", "TEXT"),
            ("operators", "offline_since", "TIMESTAMPTZ"),
        ]
        for table, col, typedef in new_cols:
            await conn.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {typedef}"
            )

        # ── Status model v2: ai / queue / in_progress / waiting / closed ─────
        await conn.execute("ALTER TABLE dialogs ALTER COLUMN status SET DEFAULT 'ai'")
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS dialogs_status_idx ON dialogs (status)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS dialogs_op_in_progress_idx "
            "ON dialogs (assigned_operator) WHERE status = 'in_progress'"
        )
        # One-shot backfill of legacy 'new' rows; guarded by a settings flag so
        # restarts are no-ops ('new' is never written again after this).
        flag = await conn.fetchval("SELECT value FROM settings WHERE key='status_model_v2'")
        if not flag:
            # Pure AI dialogs: drop the eager pre-assignment, they live in «ИИ».
            await conn.execute("""
                UPDATE dialogs SET status='ai', assigned_operator=NULL
                WHERE status='new' AND ai_enabled AND NOT operator_called
            """)
            # Drain-assigned dialogs that were never promoted to in_progress.
            await conn.execute("""
                UPDATE dialogs SET status='in_progress'
                WHERE status='new' AND assigned_operator IS NOT NULL AND NOT ai_enabled
            """)
            # Remaining 'new' = escalated but unserved → queue.
            await conn.execute("""
                UPDATE dialogs SET status='queue', assigned_operator=NULL, queued_at=NOW()
                WHERE status='new'
            """)
            # Defensive: in_progress must always have an operator.
            await conn.execute("""
                UPDATE dialogs SET status='queue', queued_at=NOW()
                WHERE status='in_progress' AND assigned_operator IS NULL
            """)
            # Start SLA clocks for live in-progress tickets.
            await conn.execute("""
                UPDATE dialogs SET sla_started_at=NOW()
                WHERE status='in_progress' AND sla_started_at IS NULL
            """)
            await conn.execute(
                "INSERT INTO settings (key, value) VALUES ('status_model_v2', '1') "
                "ON CONFLICT (key) DO NOTHING"
            )

    # ── Dialogs ───────────────────────────────────────────────────────────────

    async def upsert_dialog(
        self, dialog_id: str, chat_id: str,
        ai_enabled: bool = True, user_info: dict = None,
    ) -> dict:
        ui = user_info or {}
        existing = await self.pool.fetchrow(
            "SELECT status FROM dialogs WHERE dialog_id = $1", dialog_id
        )
        is_new = existing is None
        was_closed = existing is not None and existing["status"] == "closed"
        row = await self.pool.fetchrow(
            """
            INSERT INTO dialogs (
                dialog_id, chat_id, ai_enabled,
                user_name, user_username, user_plan, user_sub_status,
                user_next_payment, user_traffic_used, user_traffic_total,
                last_payment_amount, last_payment_date, user_photo_url, unread_count,
                status, queued_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13, 1,
                      CASE WHEN $3 THEN 'ai' ELSE 'queue' END,
                      CASE WHEN $3 THEN NULL ELSE NOW() END)
            ON CONFLICT (dialog_id) DO UPDATE SET
                ai_enabled          = CASE WHEN dialogs.status='closed' THEN $3 ELSE dialogs.ai_enabled END,
                status              = CASE WHEN dialogs.status='closed'
                                           THEN (CASE WHEN $3 THEN 'ai' ELSE 'queue' END)
                                           ELSE dialogs.status END,
                queued_at           = CASE WHEN dialogs.status='closed'
                                           THEN (CASE WHEN $3 THEN NULL ELSE NOW() END)
                                           ELSE dialogs.queued_at END,
                waiting_reason      = CASE WHEN dialogs.status='closed' THEN NULL ELSE dialogs.waiting_reason END,
                return_requested_at = CASE WHEN dialogs.status='closed' THEN NULL ELSE dialogs.return_requested_at END,
                sla_seconds_total   = CASE WHEN dialogs.status='closed' THEN 0 ELSE dialogs.sla_seconds_total END,
                sla_started_at      = CASE WHEN dialogs.status='closed' THEN NULL ELSE dialogs.sla_started_at END,
                closed_at           = CASE WHEN dialogs.status='closed' THEN NULL ELSE dialogs.closed_at END,
                assigned_operator   = CASE WHEN dialogs.status='closed' THEN NULL ELSE dialogs.assigned_operator END,
                operator_called     = CASE WHEN dialogs.status='closed' THEN FALSE ELSE dialogs.operator_called END,
                user_name           = COALESCE(EXCLUDED.user_name,          dialogs.user_name),
                user_username       = COALESCE(EXCLUDED.user_username,      dialogs.user_username),
                user_plan           = COALESCE(EXCLUDED.user_plan,          dialogs.user_plan),
                user_sub_status     = COALESCE(EXCLUDED.user_sub_status,    dialogs.user_sub_status),
                user_next_payment   = COALESCE(EXCLUDED.user_next_payment,  dialogs.user_next_payment),
                user_traffic_used   = COALESCE(EXCLUDED.user_traffic_used,  dialogs.user_traffic_used),
                user_traffic_total  = COALESCE(EXCLUDED.user_traffic_total, dialogs.user_traffic_total),
                last_payment_amount = COALESCE(EXCLUDED.last_payment_amount,dialogs.last_payment_amount),
                last_payment_date   = COALESCE(EXCLUDED.last_payment_date,  dialogs.last_payment_date),
                user_photo_url      = COALESCE(EXCLUDED.user_photo_url,     dialogs.user_photo_url),
                unread_count        = dialogs.unread_count + 1,
                updated_at          = NOW()
            RETURNING *
            """,
            dialog_id, chat_id, ai_enabled,
            ui.get("user_name"), ui.get("user_username"),
            ui.get("user_plan", "Basic"), ui.get("user_sub_status", "active"),
            ui.get("user_next_payment"),
            float(ui.get("user_traffic_used") or 0),
            float(ui.get("user_traffic_total") or 100),
            ui.get("user_last_payment_amount"), ui.get("user_last_payment_date"),
            ui.get("user_photo_url"),
        )
        return {**dict(row), "is_new_dialog": is_new or was_closed}

    async def get_all_dialogs(self) -> list[dict]:
        rows = await self.pool.fetch("SELECT * FROM dialogs ORDER BY updated_at DESC")
        return [dict(r) for r in rows]

    async def get_dialog(self, dialog_id: str) -> Optional[dict]:
        row = await self.pool.fetchrow("SELECT * FROM dialogs WHERE dialog_id = $1", dialog_id)
        return dict(row) if row else None

    async def get_active_dialog_by_chat_id(self, chat_id: str, exclude_dialog_id: str = "") -> Optional[dict]:
        row = await self.pool.fetchrow(
            "SELECT * FROM dialogs WHERE chat_id=$1 AND status != 'closed' AND dialog_id != $2 LIMIT 1",
            chat_id, exclude_dialog_id,
        )
        return dict(row) if row else None

    async def get_dialog_history(self, chat_id: str, exclude_dialog_id: str = "") -> list[dict]:
        rows = await self.pool.fetch(
            """SELECT dialog_id, last_message_text, summary, status, updated_at, rating
               FROM dialogs WHERE chat_id=$1 AND status='closed' AND dialog_id!=$2
               ORDER BY updated_at DESC LIMIT 10""",
            chat_id, exclude_dialog_id,
        )
        return [dict(r) for r in rows]

    async def update_last_message(self, dialog_id: str, text: str):
        await self.pool.execute(
            "UPDATE dialogs SET last_message_text=$1, last_message_time=NOW(), updated_at=NOW() WHERE dialog_id=$2",
            text, dialog_id,
        )

    async def update_status(self, dialog_id: str, status: str):
        if status == "closed":
            await self.pool.execute(
                "UPDATE dialogs SET status=$1, updated_at=NOW(), closed_at=NOW() WHERE dialog_id=$2",
                status, dialog_id,
            )
        else:
            await self.pool.execute(
                "UPDATE dialogs SET status=$1, updated_at=NOW() WHERE dialog_id=$2",
                status, dialog_id,
            )

    async def update_ai_enabled(self, dialog_id: str, ai_enabled: bool):
        await self.pool.execute(
            "UPDATE dialogs SET ai_enabled=$1, updated_at=NOW() WHERE dialog_id=$2",
            ai_enabled, dialog_id,
        )

    async def sync_n8n_dialog_status(self, chat_id: str, status: str):
        try:
            await self.pool.execute(
                "UPDATE n8n_dialogs SET status=$1 WHERE id=(SELECT MAX(id) FROM n8n_dialogs WHERE user_id=$2)",
                status, int(chat_id),
            )
        except Exception as e:
            print(f"[sync_n8n] status update error: {e}")

    async def sync_n8n_dialog_ai_status(self, chat_id: str, ai_enabled: bool):
        try:
            await self.pool.execute(
                "UPDATE n8n_dialogs SET ai_status=$1 WHERE user_id=$2",
                ai_enabled, int(chat_id),
            )
        except Exception as e:
            print(f"[sync_n8n] ai_status update error: {e}")

    async def set_assigned_operator(self, dialog_id: str, operator_name):
        await self.pool.execute(
            "UPDATE dialogs SET assigned_operator=$1, updated_at=NOW() WHERE dialog_id=$2",
            operator_name, dialog_id,
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

    async def update_message_delivery(self, message_id: int, status: str, error: str = None):
        await self.pool.execute(
            "UPDATE messages SET delivery_status=$1, delivery_error=$2 WHERE id=$3",
            status, error, message_id,
        )

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

    async def set_operator_paused(self, op_id: int, paused: bool):
        await self.pool.execute("UPDATE operators SET paused=$1 WHERE id=$2", paused, op_id)

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

    async def get_stats(self, days: int = 14) -> dict:
        today_total = await self.pool.fetchval(
            "SELECT COUNT(*) FROM dialogs WHERE created_at::date = CURRENT_DATE"
        ) or 0
        today_closed = await self.pool.fetchval(
            "SELECT COUNT(*) FROM dialogs WHERE status='closed' AND updated_at::date = CURRENT_DATE"
        ) or 0
        ai_resolved = await self.pool.fetchval(
            "SELECT COUNT(*) FROM dialogs "
            "WHERE status='closed' AND operator_called=FALSE AND updated_at::date = CURRENT_DATE"
        ) or 0
        ai_pct = int(ai_resolved / today_closed * 100) if today_closed else 0

        # Daily counts for last N days (missing days filled with 0)
        daily_rows = await self.pool.fetch(
            """SELECT created_at::date as d, COUNT(*) as cnt
               FROM dialogs WHERE created_at >= NOW() - ($1 || ' days')::interval
               GROUP BY d ORDER BY d""",
            str(days),
        )
        daily_map = {str(r["d"]): r["cnt"] for r in daily_rows}
        today = date.today()
        daily = [
            int(daily_map.get(str(today - timedelta(days=days - 1 - i)), 0))
            for i in range(days)
        ]

        # Hourly distribution over the last 14 days
        hourly_rows = await self.pool.fetch(
            """SELECT EXTRACT(HOUR FROM created_at)::int as h, COUNT(*) as cnt
               FROM dialogs WHERE created_at >= NOW() - '14 days'::interval
               GROUP BY h ORDER BY h"""
        )
        hourly_map = {r["h"]: r["cnt"] for r in hourly_rows}
        hourly = [int(hourly_map.get(h, 0)) for h in range(24)]

        # Operator performance
        op_rows = await self.pool.fetch("SELECT * FROM operators ORDER BY id")
        operators = []
        for op in op_rows:
            closed = await self.pool.fetchval(
                "SELECT COUNT(*) FROM dialogs WHERE status='closed' AND updated_at::date = CURRENT_DATE"
            ) or 0
            operators.append({
                "id": op["id"], "name": op["name"], "tg": op["tg"],
                "role": op["role"], "online": op["online"],
                "initials": op["initials"], "color": op["color"],
                "closed": closed, "avgTime": "—",
            })

        return {
            "today_total": today_total,
            "today_closed": today_closed,
            "ai_pct": ai_pct,
            "daily": daily,
            "hourly": hourly,
            "operators": operators,
            "top_questions": await self._get_top_questions(),
        }

    async def _get_top_questions(self) -> list[dict]:
        rows = await self.pool.fetch(
            """SELECT category AS q, COUNT(*) AS count
               FROM messages
               WHERE kind='user' AND category IS NOT NULL
                 AND created_at >= NOW() - '30 days'::interval
               GROUP BY category ORDER BY count DESC LIMIT 10"""
        )
        return [{"q": r["q"], "count": r["count"]} for r in rows]

    async def get_time_stats(self, days: int = 30) -> dict:
        interval = timedelta(days=days)

        team_first = await self.pool.fetchval("""
            SELECT AVG(EXTRACT(EPOCH FROM (m.created_at - d.created_at)))
            FROM dialogs d
            JOIN LATERAL (
                SELECT created_at, operator_name FROM messages
                WHERE dialog_id = d.dialog_id AND kind = 'operator'
                ORDER BY created_at ASC LIMIT 1
            ) m ON true
            WHERE d.created_at >= NOW() - $1::interval
        """, interval)

        team_next = await self.pool.fetchval("""
            SELECT AVG(EXTRACT(EPOCH FROM (m_op.created_at - m_usr.created_at)))
            FROM messages m_op
            JOIN LATERAL (
                SELECT created_at FROM messages
                WHERE dialog_id = m_op.dialog_id AND kind = 'user'
                  AND created_at < m_op.created_at
                ORDER BY created_at DESC LIMIT 1
            ) m_usr ON true
            WHERE m_op.kind = 'operator'
              AND m_op.created_at >= NOW() - $1::interval
        """, interval)

        team_close = await self.pool.fetchval("""
            SELECT AVG(EXTRACT(EPOCH FROM (closed_at - created_at)))
            FROM dialogs
            WHERE status = 'closed' AND closed_at IS NOT NULL
              AND created_at >= NOW() - $1::interval
        """, interval)

        op_first_rows = await self.pool.fetch("""
            SELECT m.operator_name,
                   AVG(EXTRACT(EPOCH FROM (m.created_at - d.created_at))) AS avg_sec,
                   COUNT(*) AS cnt
            FROM dialogs d
            JOIN LATERAL (
                SELECT created_at, operator_name FROM messages
                WHERE dialog_id = d.dialog_id AND kind = 'operator'
                ORDER BY created_at ASC LIMIT 1
            ) m ON true
            WHERE d.created_at >= NOW() - $1::interval
              AND m.operator_name IS NOT NULL
            GROUP BY m.operator_name
        """, interval)

        op_next_rows = await self.pool.fetch("""
            SELECT m_op.operator_name,
                   AVG(EXTRACT(EPOCH FROM (m_op.created_at - m_usr.created_at))) AS avg_sec
            FROM messages m_op
            JOIN LATERAL (
                SELECT created_at FROM messages
                WHERE dialog_id = m_op.dialog_id AND kind = 'user'
                  AND created_at < m_op.created_at
                ORDER BY created_at DESC LIMIT 1
            ) m_usr ON true
            WHERE m_op.kind = 'operator'
              AND m_op.created_at >= NOW() - $1::interval
              AND m_op.operator_name IS NOT NULL
            GROUP BY m_op.operator_name
        """, interval)

        op_first_map = {r["operator_name"]: {"avg": float(r["avg_sec"]), "cnt": int(r["cnt"])}
                        for r in op_first_rows}
        op_next_map  = {r["operator_name"]: float(r["avg_sec"]) for r in op_next_rows}

        op_rows = await self.pool.fetch("SELECT * FROM operators ORDER BY id")
        operators = [{
            "id": op["id"], "name": op["name"], "online": op["online"],
            "initials": op["initials"], "color": op["color"],
            "role": op["role"], "tg": op["tg"],
            "first_response_avg": op_first_map.get(op["name"], {}).get("avg"),
            "next_response_avg":  op_next_map.get(op["name"]),
            "dialogs_count":      op_first_map.get(op["name"], {}).get("cnt", 0),
        } for op in op_rows]

        return {
            "period_days": days,
            "team": {
                "first_response_avg": float(team_first) if team_first else None,
                "next_response_avg":  float(team_next)  if team_next  else None,
                "close_time_avg":     float(team_close) if team_close else None,
            },
            "operators": operators,
        }

    # ── Knowledge Base ────────────────────────────────────────────────────────

    async def save_kb_article(self, id: str, title: str, category: str, keywords: str, content: str):
        await self.pool.execute(
            """INSERT INTO kb_articles (id, title, category, keywords, content)
               VALUES ($1,$2,$3,$4,$5)
               ON CONFLICT (id) DO UPDATE SET
                 title=EXCLUDED.title, category=EXCLUDED.category,
                 keywords=EXCLUDED.keywords, content=EXCLUDED.content""",
            id, title, category, keywords, content,
        )

    async def get_kb_articles(self) -> list[dict]:
        rows = await self.pool.fetch("SELECT * FROM kb_articles ORDER BY created_at DESC")
        return [dict(r) for r in rows]

    async def delete_kb_article(self, article_id: str) -> bool:
        result = await self.pool.execute("DELETE FROM kb_articles WHERE id=$1", article_id)
        return result == "DELETE 1"

    async def reset_kb(self):
        await self.pool.execute("TRUNCATE TABLE kb_articles")

    async def get_templates(self) -> list[dict]:
        rows = await self.pool.fetch(
            "SELECT * FROM message_templates ORDER BY group_name, title"
        )
        return [dict(r) for r in rows]

    async def save_template(self, id: int | None, group_name: str, title: str, text: str) -> dict | None:
        if id:
            row = await self.pool.fetchrow(
                "UPDATE message_templates SET group_name=$1, title=$2, text=$3 WHERE id=$4 RETURNING *",
                group_name, title, text, id,
            )
        else:
            row = await self.pool.fetchrow(
                "INSERT INTO message_templates (group_name, title, text) VALUES ($1,$2,$3) RETURNING *",
                group_name, title, text,
            )
        return dict(row) if row else None

    async def delete_template(self, template_id: int) -> bool:
        result = await self.pool.execute(
            "DELETE FROM message_templates WHERE id=$1", template_id
        )
        return result == "DELETE 1"

    async def rename_template_group(self, old_name: str, new_name: str):
        await self.pool.execute(
            "UPDATE message_templates SET group_name=$1 WHERE group_name=$2",
            new_name, old_name,
        )

    async def get_user_message_count(self, dialog_id: str) -> int:
        return await self.pool.fetchval(
            "SELECT COUNT(*) FROM messages WHERE dialog_id=$1 AND kind='user'", dialog_id
        ) or 0

    async def set_dialog_rating(self, dialog_id: str, rating: int):
        await self.pool.execute(
            "UPDATE dialogs SET rating=$1 WHERE dialog_id=$2", rating, dialog_id
        )

    async def get_all_chat_ids(self) -> list:
        rows = await self.pool.fetch(
            "SELECT DISTINCT chat_id FROM dialogs WHERE chat_id IS NOT NULL"
        )
        return [r["chat_id"] for r in rows]

    # Slot definition: only in_progress tickets occupy an operator slot.
    _FREE_OPERATOR_SQL = """
        SELECT o.name
        FROM operators o
        LEFT JOIN (
            SELECT assigned_operator, COUNT(*) AS cnt
            FROM dialogs
            WHERE status = 'in_progress' AND assigned_operator IS NOT NULL
            GROUP BY assigned_operator
        ) active ON active.assigned_operator = o.name
        WHERE o.online = TRUE
          AND COALESCE(o.paused, FALSE) = FALSE
          AND COALESCE(active.cnt, 0) < $1
        ORDER BY COALESCE(active.cnt, 0) ASC
        LIMIT 1
    """

    _CLAIM_STATE_SQL = """
        assigned_operator = $1,
        status = 'in_progress',
        sla_started_at = COALESCE(sla_started_at, NOW()),
        waiting_reason = NULL,
        queued_at = NULL,
        return_requested_at = NULL,
        updated_at = NOW()
    """

    async def assign_dialog(self, dialog_id: str, max_tickets: int) -> str | None:
        """Hand the dialog to the least-loaded online operator with a free slot,
        atomically setting the full in_progress state (SLA start included).
        Uses an advisory lock so concurrent claims don't exceed max_tickets."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1)", self._ASSIGN_LOCK)
                row = await conn.fetchrow(self._FREE_OPERATOR_SQL, max_tickets)
                if not row:
                    return None
                op_name = row["name"]
                await conn.execute(
                    f"UPDATE dialogs SET {self._CLAIM_STATE_SQL} WHERE dialog_id = $2",
                    op_name, dialog_id,
                )
                return op_name

    async def claim_next_queued(self, max_tickets: int) -> dict | None:
        """Atomically bind the oldest queued dialog (status='queue' only — never
        AI-handled ones) to the least-loaded online operator with capacity.
        Returns {'dialog': dict, 'op_name': str} or None."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1)", self._ASSIGN_LOCK)
                op_row = await conn.fetchrow(self._FREE_OPERATOR_SQL, max_tickets)
                if not op_row:
                    return None
                dialog_row = await conn.fetchrow(f"""
                    UPDATE dialogs SET {self._CLAIM_STATE_SQL}
                    WHERE dialog_id = (
                        SELECT dialog_id FROM dialogs
                        WHERE status = 'queue'
                        ORDER BY COALESCE(queued_at, created_at) ASC LIMIT 1
                    )
                    RETURNING *
                """, op_row["name"])
                if not dialog_row:
                    return None
                return {"dialog": dict(dialog_row), "op_name": op_row["name"]}

    async def claim_pending_return(self, max_tickets: int) -> dict | None:
        """Return the oldest waiting dialog whose client already replied
        (return_requested_at set) to ITS OWN operator, provided that operator is
        online and has a free slot. Ignores 'paused' — it's the operator's own
        ticket coming back. Returns {'dialog': dict, 'op_name': str} or None."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1)", self._ASSIGN_LOCK)
                dialog_row = await conn.fetchrow("""
                    UPDATE dialogs SET
                        status = 'in_progress',
                        sla_started_at = COALESCE(sla_started_at, NOW()),
                        waiting_reason = NULL,
                        queued_at = NULL,
                        return_requested_at = NULL,
                        updated_at = NOW()
                    WHERE dialog_id = (
                        SELECT d.dialog_id
                        FROM dialogs d
                        JOIN operators o ON o.name = d.assigned_operator
                        LEFT JOIN (
                            SELECT assigned_operator, COUNT(*) AS cnt
                            FROM dialogs
                            WHERE status = 'in_progress' AND assigned_operator IS NOT NULL
                            GROUP BY assigned_operator
                        ) active ON active.assigned_operator = o.name
                        WHERE d.status = 'waiting'
                          AND d.return_requested_at IS NOT NULL
                          AND o.online = TRUE
                          AND COALESCE(active.cnt, 0) < $1
                        ORDER BY d.return_requested_at ASC
                        LIMIT 1
                    )
                    RETURNING *
                """, max_tickets)
                if not dialog_row:
                    return None
                return {"dialog": dict(dialog_row), "op_name": dialog_row["assigned_operator"]}

    # ── Status-model transitions (single-statement, SLA-safe) ────────────────

    _SLA_PAUSE_SQL = """
        sla_seconds_total = sla_seconds_total + CASE WHEN sla_started_at IS NOT NULL
            THEN GREATEST(0, EXTRACT(EPOCH FROM (NOW() - sla_started_at)))::int ELSE 0 END,
        sla_started_at = NULL
    """

    async def move_to_queue(self, dialog_id: str):
        """→ queue: unassign, stamp queued_at, clear waiting fields, pause SLA."""
        await self.pool.execute(f"""
            UPDATE dialogs SET
                status='queue', assigned_operator=NULL, queued_at=NOW(),
                waiting_reason=NULL, return_requested_at=NULL, closed_at=NULL,
                {self._SLA_PAUSE_SQL},
                updated_at=NOW()
            WHERE dialog_id=$1
        """, dialog_id)

    async def move_to_waiting(self, dialog_id: str, reason: str):
        """→ waiting ('operator_replied' | 'manual'): keep binding, pause SLA."""
        await self.pool.execute(f"""
            UPDATE dialogs SET
                status='waiting', waiting_reason=$2, return_requested_at=NULL,
                {self._SLA_PAUSE_SQL},
                updated_at=NOW()
            WHERE dialog_id=$1
        """, dialog_id, reason)

    async def move_to_in_progress(self, dialog_id: str, op_name: str):
        """→ in_progress bound to op_name, bypassing slot limits (manual take /
        transfer / own-ticket return decided by the caller). Starts SLA."""
        await self.pool.execute(f"""
            UPDATE dialogs SET {self._CLAIM_STATE_SQL}
            WHERE dialog_id = $2
        """, op_name, dialog_id)

    async def move_to_ai(self, dialog_id: str):
        """→ ai section (AI re-enabled on an unassigned ticket)."""
        await self.pool.execute(f"""
            UPDATE dialogs SET
                status='ai', assigned_operator=NULL, operator_called=FALSE,
                queued_at=NULL, waiting_reason=NULL, return_requested_at=NULL,
                {self._SLA_PAUSE_SQL},
                updated_at=NOW()
            WHERE dialog_id=$1
        """, dialog_id)

    async def move_to_closed(self, dialog_id: str):
        """→ closed: pause SLA, clear waiting fields, stamp closed_at."""
        await self.pool.execute(f"""
            UPDATE dialogs SET
                status='closed', closed_at=NOW(), operator_called=FALSE,
                waiting_reason=NULL, queued_at=NULL, return_requested_at=NULL,
                {self._SLA_PAUSE_SQL},
                updated_at=NOW()
            WHERE dialog_id=$1
        """, dialog_id)

    async def set_return_requested(self, dialog_id: str):
        """Mark a waiting ticket as 'client replied, wants to come back'."""
        await self.pool.execute(
            "UPDATE dialogs SET return_requested_at=COALESCE(return_requested_at, NOW()), "
            "updated_at=NOW() WHERE dialog_id=$1",
            dialog_id,
        )

    async def get_return_requested_dialogs(self) -> list[dict]:
        rows = await self.pool.fetch(
            "SELECT * FROM dialogs WHERE status='waiting' AND return_requested_at IS NOT NULL "
            "ORDER BY return_requested_at ASC"
        )
        return [dict(r) for r in rows]

    async def get_operator_dialogs_by_status(self, op_name: str, status: str) -> list[dict]:
        rows = await self.pool.fetch(
            "SELECT * FROM dialogs WHERE assigned_operator=$1 AND status=$2",
            op_name, status,
        )
        return [dict(r) for r in rows]

    async def set_operator_offline_since(self, op_id: int, offline: bool):
        """Stamp/clear the offline-grace timer for an operator."""
        if offline:
            await self.pool.execute(
                "UPDATE operators SET offline_since=NOW() WHERE id=$1", op_id
            )
        else:
            await self.pool.execute(
                "UPDATE operators SET offline_since=NULL WHERE id=$1", op_id
            )

    async def get_offline_expired_operators(self, grace_seconds: int) -> list[dict]:
        """Operators offline for longer than the grace period (timer not yet consumed)."""
        rows = await self.pool.fetch(
            """SELECT * FROM operators
               WHERE COALESCE(online, FALSE) = FALSE
                 AND offline_since IS NOT NULL
                 AND offline_since < NOW() - ($1 || ' seconds')::interval""",
            str(int(grace_seconds)),
        )
        return [dict(r) for r in rows]

    async def is_operator_within_grace(self, op_name: str, grace_seconds: int) -> bool:
        """True if the ticket's operator might still come back: online, or offline
        for less than the grace period. Unknown operators are treated as gone."""
        row = await self.pool.fetchrow(
            "SELECT online, offline_since FROM operators WHERE name=$1", op_name
        )
        if not row:
            return False
        if row["online"]:
            return True
        if row["offline_since"] is None:
            return False
        remaining = await self.pool.fetchval(
            "SELECT $1::timestamptz > NOW() - ($2 || ' seconds')::interval",
            row["offline_since"], str(int(grace_seconds)),
        )
        return bool(remaining)

    async def get_operator_by_name(self, name: str) -> dict | None:
        row = await self.pool.fetchrow("SELECT * FROM operators WHERE name=$1", name)
        return dict(row) if row else None

    async def close(self):
        if self.pool:
            await self.pool.close()
