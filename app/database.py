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

    # ── Dialogs ───────────────────────────────────────────────────────────────

    async def upsert_dialog(
        self, dialog_id: str, chat_id: str,
        ai_enabled: bool = True, user_info: dict = None,
    ) -> dict:
        ui = user_info or {}
        row = await self.pool.fetchrow(
            """
            INSERT INTO dialogs (
                dialog_id, chat_id, ai_enabled,
                user_name, user_username, user_plan, user_sub_status,
                user_next_payment, user_traffic_used, user_traffic_total,
                last_payment_amount, last_payment_date, unread_count
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12, 1)
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
        )
        return dict(row)

    async def get_all_dialogs(self) -> list[dict]:
        rows = await self.pool.fetch("SELECT * FROM dialogs ORDER BY updated_at DESC")
        return [dict(r) for r in rows]

    async def get_dialog(self, dialog_id: str) -> Optional[dict]:
        row = await self.pool.fetchrow("SELECT * FROM dialogs WHERE dialog_id = $1", dialog_id)
        return dict(row) if row else None

    async def get_dialog_history(self, chat_id: str, exclude_dialog_id: str = "") -> list[dict]:
        rows = await self.pool.fetch(
            """SELECT dialog_id, last_message_text, summary, status, updated_at
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
        interval = f"{days} days"

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

    async def auto_assign_dialog(self, dialog_id: str, max_tickets: int) -> str | None:
        """Find the least-loaded online operator and assign dialog_id to them.
        Uses an advisory lock so concurrent calls don't exceed max_tickets."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1)", self._ASSIGN_LOCK)
                row = await conn.fetchrow("""
                    SELECT o.name
                    FROM operators o
                    LEFT JOIN (
                        SELECT assigned_operator, COUNT(*) AS cnt
                        FROM dialogs
                        WHERE status != 'closed' AND assigned_operator IS NOT NULL
                        GROUP BY assigned_operator
                    ) active ON active.assigned_operator = o.name
                    WHERE o.online = TRUE
                      AND COALESCE(active.cnt, 0) < $1
                    ORDER BY COALESCE(active.cnt, 0) ASC
                    LIMIT 1
                """, max_tickets)
                if not row:
                    return None
                op_name = row["name"]
                await conn.execute(
                    "UPDATE dialogs SET assigned_operator=$1, updated_at=NOW() WHERE dialog_id=$2",
                    op_name, dialog_id,
                )
                return op_name

    async def claim_next_assignment(self, max_tickets: int) -> dict | None:
        """Atomically find the least-loaded online operator with capacity AND the oldest
        queued dialog, assign them. Returns {'dialog': dict, 'op_name': str} or None."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1)", self._ASSIGN_LOCK)
                op_row = await conn.fetchrow("""
                    SELECT o.name
                    FROM operators o
                    LEFT JOIN (
                        SELECT assigned_operator, COUNT(*) AS cnt
                        FROM dialogs
                        WHERE status != 'closed' AND assigned_operator IS NOT NULL
                        GROUP BY assigned_operator
                    ) active ON active.assigned_operator = o.name
                    WHERE o.online = TRUE AND COALESCE(active.cnt, 0) < $1
                    ORDER BY COALESCE(active.cnt, 0) ASC
                    LIMIT 1
                """, max_tickets)
                if not op_row:
                    return None
                dialog_row = await conn.fetchrow("""
                    UPDATE dialogs SET assigned_operator = $1, updated_at = NOW()
                    WHERE dialog_id = (
                        SELECT dialog_id FROM dialogs
                        WHERE assigned_operator IS NULL AND status != 'closed'
                        ORDER BY created_at ASC LIMIT 1
                    )
                    RETURNING *
                """, op_row["name"])
                if not dialog_row:
                    return None
                return {"dialog": dict(dialog_row), "op_name": op_row["name"]}

    async def get_operator_by_name(self, name: str) -> dict | None:
        row = await self.pool.fetchrow("SELECT * FROM operators WHERE name=$1", name)
        return dict(row) if row else None

    async def close(self):
        if self.pool:
            await self.pool.close()
