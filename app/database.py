import asyncpg
import json
from datetime import datetime, timezone
from typing import Optional
from app.config import Settings

_AVATAR_COLORS = ["#4F8EF7", "#A855F7", "#22c55e", "#eab308", "#ef4444", "#06b6d4", "#f97316"]


def avatar_color(dialog_id: str) -> str:
    return _AVATAR_COLORS[hash(dialog_id) % len(_AVATAR_COLORS)]


def make_initials(name: str) -> str:
    if not name:
        return "??"
    parts = name.split()
    return "".join(p[0] for p in parts[:2]).upper()


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
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS dialogs (
                dialog_id            TEXT PRIMARY KEY,
                chat_id              TEXT NOT NULL,
                status               TEXT NOT NULL DEFAULT 'new',
                ai_enabled           BOOLEAN NOT NULL DEFAULT TRUE,
                operator_called      BOOLEAN NOT NULL DEFAULT FALSE,
                unread_count         INTEGER NOT NULL DEFAULT 0,
                user_name            TEXT,
                user_username        TEXT,
                user_plan            TEXT DEFAULT 'Basic',
                user_sub_status      TEXT DEFAULT 'active',
                user_next_payment    TEXT,
                user_traffic_used    FLOAT DEFAULT 0,
                user_traffic_total   FLOAT DEFAULT 100,
                last_payment_amount  TEXT,
                last_payment_date    TEXT,
                last_message_text    TEXT,
                last_message_time    TIMESTAMP DEFAULT NOW(),
                created_at           TIMESTAMP DEFAULT NOW(),
                updated_at           TIMESTAMP DEFAULT NOW()
            )
        """)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id            SERIAL PRIMARY KEY,
                dialog_id     TEXT NOT NULL REFERENCES dialogs(dialog_id) ON DELETE CASCADE,
                kind          TEXT NOT NULL,
                text          TEXT,
                file_id       TEXT,
                file_type     TEXT,
                file_url      TEXT,
                operator_name TEXT,
                created_at    TIMESTAMP DEFAULT NOW()
            )
        """)
        await self.pool.execute("""
            CREATE INDEX IF NOT EXISTS messages_dialog_idx ON messages (dialog_id, created_at)
        """)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS operators (
                id         SERIAL PRIMARY KEY,
                name       TEXT NOT NULL,
                tg         TEXT,
                role       TEXT NOT NULL DEFAULT 'agent',
                online     BOOLEAN DEFAULT FALSE,
                initials   TEXT,
                color      TEXT DEFAULT '#4F8EF7',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        print("✅ Database initialized")

    # ── Dialogs ───────────────────────────────────────────────────────────────

    async def upsert_dialog(self, dialog_id: str, chat_id: str, ai_enabled: bool = True, user_info: dict = None) -> dict:
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
            RETURNING *
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
            """SELECT dialog_id, last_message_text, status, updated_at
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
        await self.pool.execute("UPDATE dialogs SET unread_count=0 WHERE dialog_id=$1", dialog_id)

    # ── Messages ──────────────────────────────────────────────────────────────

    async def save_message(self, dialog_id: str, kind: str, text: str = None,
                           file_id: str = None, file_type: str = None,
                           file_url: str = None, operator_name: str = None) -> dict:
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

    # ── Operators ─────────────────────────────────────────────────────────────

    async def get_operators(self) -> list[dict]:
        rows = await self.pool.fetch("SELECT * FROM operators ORDER BY id")
        return [dict(r) for r in rows]

    async def create_operator(self, name: str, tg: str, role: str) -> dict:
        initials = make_initials(name)
        colors = ["#A855F7", "#4F8EF7", "#22c55e", "#eab308", "#f97316", "#ef4444", "#06b6d4"]
        count = await self.pool.fetchval("SELECT COUNT(*) FROM operators")
        color = colors[count % len(colors)]
        row = await self.pool.fetchrow(
            "INSERT INTO operators (name, tg, role, initials, color) VALUES ($1,$2,$3,$4,$5) RETURNING *",
            name, tg, role, initials, color,
        )
        return dict(row)

    async def update_operator(self, op_id: int, name: str, tg: str, role: str) -> Optional[dict]:
        initials = make_initials(name)
        row = await self.pool.fetchrow(
            "UPDATE operators SET name=$1, tg=$2, role=$3, initials=$4 WHERE id=$5 RETURNING *",
            name, tg, role, initials, op_id,
        )
        return dict(row) if row else None

    async def delete_operator(self, op_id: int) -> bool:
        result = await self.pool.execute("DELETE FROM operators WHERE id=$1", op_id)
        return result == "DELETE 1"

    async def set_operator_online(self, op_id: int, online: bool):
        await self.pool.execute("UPDATE operators SET online=$1 WHERE id=$2", online, op_id)

    # ── Settings ──────────────────────────────────────────────────────────────

    async def get_setting(self, key: str) -> Optional[str]:
        row = await self.pool.fetchrow("SELECT value FROM settings WHERE key=$1", key)
        return row["value"] if row else None

    async def set_setting(self, key: str, value: str):
        await self.pool.execute(
            "INSERT INTO settings (key,value) VALUES ($1,$2) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()",
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
            "SELECT COUNT(*) FROM dialogs WHERE status='closed' AND operator_called=FALSE AND updated_at::date = CURRENT_DATE"
        ) or 0
        ai_pct = int(ai_resolved / today_closed * 100) if today_closed else 0

        # Daily counts for last N days (fill missing days with 0)
        daily_rows = await self.pool.fetch(
            """SELECT created_at::date as d, COUNT(*) as cnt
               FROM dialogs WHERE created_at >= NOW() - ($1 || ' days')::interval
               GROUP BY d ORDER BY d""",
            str(days),
        )
        daily_map = {str(r["d"]): r["cnt"] for r in daily_rows}
        from datetime import date, timedelta
        today = date.today()
        daily = [int(daily_map.get(str(today - timedelta(days=days - 1 - i)), 0)) for i in range(days)]

        # Hourly distribution (last 14 days)
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
        }

    async def close(self):
        if self.pool:
            await self.pool.close()
