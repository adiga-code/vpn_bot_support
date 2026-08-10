import json
import re
from datetime import date, timedelta
from typing import Optional

import asyncpg

from app.config import Settings

_AVATAR_COLORS = ["#4F8EF7", "#A855F7", "#22c55e", "#eab308", "#ef4444", "#06b6d4", "#f97316"]

# settings.service_id = 0 — глобальная настройка (звуки, флаги миграций).
# Ноль, а не NULL: колонка входит в PRIMARY KEY, а тот не допускает NULL.
GLOBAL_SERVICE_ID = 0

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}$")


# ── Helpers ───────────────────────────────────────────────────────────────────

def validate_slug(slug: str) -> str:
    """Slug сервиса попадает в ключи Redis, имена коллекций Qdrant и DDL —
    пускаем только безопасный алфавит."""
    slug = (slug or "").strip().lower()
    if not _SLUG_RE.match(slug):
        raise ValueError(
            "Слаг сервиса: латиница в нижнем регистре, цифры, дефис и подчёркивание, "
            "до 31 символа, первый символ — буква или цифра"
        )
    return slug


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
                "ON CONFLICT DO NOTHING"
            )

        await self._migrate_services(conn)

    async def _migrate_services(self, conn):
        """Слой мультитенантности: каждый ВПН — строка в services, со своими
        диалогами, базой знаний, шаблонами и настройками. Доступ оператора к
        сервису — флаг в operator_services; админ видит все активные сервисы
        без флагов."""
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id                SERIAL PRIMARY KEY,
                slug              TEXT UNIQUE NOT NULL,
                name              TEXT NOT NULL,
                color             TEXT NOT NULL DEFAULT '#4F8EF7',
                emoji             TEXT,
                qdrant_collection TEXT NOT NULL,
                dialog_id_prefix  TEXT NOT NULL DEFAULT '',
                n8n_webhook_url   TEXT NOT NULL DEFAULT '',
                is_active         BOOLEAN NOT NULL DEFAULT TRUE,
                sort_order        INTEGER NOT NULL DEFAULT 0,
                created_at        TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        # business_connection_id — то, что Telegram присылает с каждым
        # сообщением из подключённого к боту аккаунта поддержки. По нему панель
        # понимает, какому ВПН-у принадлежит тикет, поэтому в n8n больше не
        # нужен слаг в переменной.
        await conn.execute(
            "ALTER TABLE services ADD COLUMN IF NOT EXISTS "
            "business_connection_id TEXT NOT NULL DEFAULT ''"
        )
        # Индекс частичный: пустая строка у сервисов без business-аккаунта
        # встречается сколько угодно раз, а занятый id — ровно один раз, иначе
        # сообщения одного аккаунта уехали бы в два ВПН-а.
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS services_business_connection_id_key
            ON services (business_connection_id) WHERE business_connection_id <> ''
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS operator_services (
                operator_id INTEGER NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
                service_id  INTEGER NOT NULL REFERENCES services(id)  ON DELETE CASCADE,
                PRIMARY KEY (operator_id, service_id)
            )
        """)

        # message_templates.service_id остаётся NULL-able: NULL = общий шаблон.
        for table in ("dialogs", "kb_articles", "message_templates"):
            await conn.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS service_id INTEGER "
                f"REFERENCES services(id) ON DELETE CASCADE"
            )
        await conn.execute(
            f"ALTER TABLE settings ADD COLUMN IF NOT EXISTS service_id INTEGER "
            f"NOT NULL DEFAULT {GLOBAL_SERVICE_ID}"
        )
        # PK settings: key → (key, service_id), чтобы одинаковые ключи жили
        # рядом у разных сервисов.
        pk_cols = await conn.fetchval("""
            SELECT COUNT(*) FROM information_schema.key_column_usage
            WHERE table_schema='public' AND table_name='settings'
              AND constraint_name='settings_pkey'
        """)
        if pk_cols == 1:
            await conn.execute("ALTER TABLE settings DROP CONSTRAINT settings_pkey")
            await conn.execute("ALTER TABLE settings ADD PRIMARY KEY (key, service_id)")

        slug = validate_slug(self.settings.DEFAULT_SERVICE_SLUG)

        # n8n делит с хелпдеском n8n_dialogs/n8n_messages и ищет по user_id.
        # Без сервиса один и тот же Telegram-юзер, написавший в два бота,
        # схлопывается в одну запись — добавляем разделитель.
        for table in ("n8n_dialogs", "n8n_messages"):
            await conn.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS service TEXT "
                f"NOT NULL DEFAULT '{slug}'"
            )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS n8n_dialogs_user_service_idx "
            "ON n8n_dialogs (user_id, service)"
        )

        # ── Одноразовый бэкфилл ───────────────────────────────────────────────
        flag = await conn.fetchval(
            "SELECT value FROM settings WHERE key='multi_tenant_v1' AND service_id=$1",
            GLOBAL_SERVICE_ID,
        )
        if not flag:
            # Коллекция Qdrant у мигрированного сервиса остаётся прежней ('kb'),
            # а префикс dialog_id — пустым: существующие векторы и первичные
            # ключи диалогов не трогаем, переиндексация не нужна.
            default_id = await conn.fetchval(
                """INSERT INTO services (slug, name, qdrant_collection, dialog_id_prefix, sort_order)
                   VALUES ($1, $2, 'kb', '', 0)
                   ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
                   RETURNING id""",
                slug, self.settings.DEFAULT_SERVICE_NAME,
            )
            for table in ("dialogs", "kb_articles", "message_templates"):
                await conn.execute(
                    f"UPDATE {table} SET service_id=$1 WHERE service_id IS NULL", default_id
                )
            # Контентные настройки становятся пер-сервисными целиком; глобальными
            # остаются только звуки и флаги миграций.
            await conn.execute(
                "UPDATE settings SET service_id=$1 "
                "WHERE service_id=$2 AND key IN ('ai_settings','automation','schedule')",
                default_id, GLOBAL_SERVICE_ID,
            )
            # Без флагов операторы разом потеряли бы все свои тикеты.
            await conn.execute(
                "INSERT INTO operator_services (operator_id, service_id) "
                "SELECT id, $1 FROM operators ON CONFLICT DO NOTHING",
                default_id,
            )
            await conn.execute(
                "INSERT INTO settings (key, value, service_id) "
                "VALUES ('multi_tenant_v1', '1', $1) ON CONFLICT DO NOTHING",
                GLOBAL_SERVICE_ID,
            )
            print(f"[migrate] multi-tenant: сервис по умолчанию '{slug}' (id={default_id})")

        # Диалог и статья БЗ всегда принадлежат сервису (после бэкфилла NULL-ов нет).
        await conn.execute("ALTER TABLE dialogs     ALTER COLUMN service_id SET NOT NULL")
        await conn.execute("ALTER TABLE kb_articles ALTER COLUMN service_id SET NOT NULL")

        await conn.execute(
            "CREATE INDEX IF NOT EXISTS dialogs_service_status_idx ON dialogs (service_id, status)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS dialogs_service_chat_idx ON dialogs (service_id, chat_id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS kb_articles_service_idx ON kb_articles (service_id)"
        )

        await self._migrate_monitoring(conn)
        await self._migrate_customer(conn)

    async def _migrate_monitoring(self, conn):
        """Мониторинг серверов был глобальным (SERVERS в .env) — переносим его в
        пер-сервисную настройку `monitoring` первого сервиса, чтобы установка с
        настроенными серверами не откатилась на мок. Отдельный флаг: базы,
        мигрировавшие на мультитенантность раньше, тоже должны это получить."""
        flag = await conn.fetchval(
            "SELECT value FROM settings WHERE key='monitoring_v1' AND service_id=$1",
            GLOBAL_SERVICE_ID,
        )
        if flag:
            return
        try:
            servers = json.loads(self.settings.SERVERS or "[]")
        except Exception:
            servers = []
        monitor_type = (self.settings.SERVERS_MONITOR_TYPE or "stub").lower()
        # "stub" — прежнее имя мока в конфиге; провайдер называется "mock".
        provider = "mock" if not servers or monitor_type == "stub" else monitor_type
        config = {"servers": servers} if servers else {}
        if provider == "http":
            config["health_path"] = self.settings.SERVERS_HEALTH_PATH
        row = await conn.fetchrow("SELECT id FROM services ORDER BY sort_order, id LIMIT 1")
        if row:
            monitoring = {
                "interval": int(self.settings.SERVERS_CHECK_INTERVAL or 300),
                "servers": {"provider": provider, "config": config},
                "bots": {"provider": "mock_bot", "config": {}},
            }
            await conn.execute(
                "INSERT INTO settings (key, value, service_id) VALUES ('monitoring', $1, $2) "
                "ON CONFLICT (key, service_id) DO NOTHING",
                json.dumps(monitoring, ensure_ascii=False), row["id"],
            )
            print(f"[migrate] monitoring: провайдер серверов '{provider}' у сервиса id={row['id']}")
        await conn.execute(
            "INSERT INTO settings (key, value, service_id) VALUES ('monitoring_v1','1',$1) "
            "ON CONFLICT DO NOTHING",
            GLOBAL_SERVICE_ID,
        )

    async def _migrate_customer(self, conn):
        """Прежний биллинг настраивался глобально (BILLING_API_URL в .env) и умел
        три действия. Он поглощён пер-сервисной настройкой `customer`: переносим
        адрес и токен в первый сервис, чтобы установка с настроенным биллингом не
        откатилась на мок."""
        flag = await conn.fetchval(
            "SELECT value FROM settings WHERE key='customer_v1' AND service_id=$1",
            GLOBAL_SERVICE_ID,
        )
        if flag:
            return
        url = (self.settings.BILLING_API_URL or "").strip()
        row = await conn.fetchrow("SELECT id FROM services ORDER BY sort_order, id LIMIT 1")
        if url and row:
            customer = {
                "provider": "http",
                "config": {"base_url": url, "token": self.settings.BILLING_API_TOKEN or "",
                           # Прежний биллинг умел только эти три действия —
                           # остальные кнопки не показываем, пока админ не
                           # проверит, что его API их поддерживает.
                           "paths": {
                               "renew": "POST /subscriptions/renew",
                               "buy_traffic": "POST /subscriptions/buy_traffic",
                               "reset_key": "POST /keys/reset",
                           }},
                "cacheTtl": 60,
            }
            await conn.execute(
                "INSERT INTO settings (key, value, service_id) VALUES ('customer', $1, $2) "
                "ON CONFLICT (key, service_id) DO NOTHING",
                json.dumps(customer, ensure_ascii=False), row["id"],
            )
            print(f"[migrate] customer: биллинг перенесён в сервис id={row['id']}")
        await conn.execute(
            "INSERT INTO settings (key, value, service_id) VALUES ('customer_v1','1',$1) "
            "ON CONFLICT DO NOTHING",
            GLOBAL_SERVICE_ID,
        )

    # ── Services ──────────────────────────────────────────────────────────────

    async def get_services(self, only_active: bool = True) -> list[dict]:
        rows = await self.pool.fetch(
            "SELECT * FROM services WHERE ($1 = FALSE OR is_active) ORDER BY sort_order, id",
            only_active,
        )
        return [dict(r) for r in rows]

    async def get_service(self, service_id: int) -> Optional[dict]:
        row = await self.pool.fetchrow("SELECT * FROM services WHERE id=$1", service_id)
        return dict(row) if row else None

    async def get_service_by_slug(self, slug: str) -> Optional[dict]:
        row = await self.pool.fetchrow("SELECT * FROM services WHERE slug=$1", slug)
        return dict(row) if row else None

    async def get_service_by_business_id(self, business_id: str) -> Optional[dict]:
        """Сервис по business_connection_id аккаунта поддержки. Пустую строку
        не ищем: она стоит у всех сервисов без business-аккаунта."""
        if not business_id:
            return None
        row = await self.pool.fetchrow(
            "SELECT * FROM services WHERE business_connection_id=$1", str(business_id)
        )
        return dict(row) if row else None

    async def create_service(
        self, slug: str, name: str, color: str = "#4F8EF7", emoji: str = None,
        n8n_webhook_url: str = "", business_connection_id: str = "",
    ) -> dict:
        """Новый сервис получает собственную коллекцию Qdrant и префикс
        dialog_id — так диалоги двух независимых n8n не столкнутся первичными
        ключами, а базы знаний не смешаются."""
        slug = validate_slug(slug)
        sort_order = await self.pool.fetchval(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM services"
        )
        row = await self.pool.fetchrow(
            """INSERT INTO services (slug, name, color, emoji, qdrant_collection,
                                     dialog_id_prefix, n8n_webhook_url, sort_order,
                                     business_connection_id)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *""",
            slug, name, color, emoji, f"kb_{slug}", f"{slug}_", n8n_webhook_url or "", sort_order,
            (business_connection_id or "").strip(),
        )
        return dict(row)

    async def update_service(
        self, service_id: int, name: str, color: str, emoji: str = None,
        n8n_webhook_url: str = "", is_active: bool = True,
        business_connection_id: str = "",
    ) -> Optional[dict]:
        """slug, коллекция Qdrant и префикс dialog_id неизменяемы: они уже
        зашиты в воркфлоу n8n, в ключи Redis и в первичные ключи диалогов.
        business_connection_id, наоборот, меняется: аккаунт поддержки
        переподключают к боту, и Telegram выдаёт новый id."""
        row = await self.pool.fetchrow(
            """UPDATE services SET name=$1, color=$2, emoji=$3, n8n_webhook_url=$4, is_active=$5,
                                   business_connection_id=$6
               WHERE id=$7 RETURNING *""",
            name, color, emoji, n8n_webhook_url or "", is_active,
            (business_connection_id or "").strip(), service_id,
        )
        return dict(row) if row else None

    async def delete_service(self, service_id: int) -> bool:
        result = await self.pool.execute("DELETE FROM services WHERE id=$1", service_id)
        await self.pool.execute("DELETE FROM settings WHERE service_id=$1", service_id)
        return result == "DELETE 1"

    async def get_operator_service_ids(self, operator: dict) -> list[int]:
        """Сервисы, доступные оператору. Админ видит все активные без флагов."""
        if operator.get("role") == "admin":
            rows = await self.pool.fetch(
                "SELECT id FROM services WHERE is_active ORDER BY sort_order, id"
            )
        else:
            rows = await self.pool.fetch(
                """SELECT s.id FROM services s
                   JOIN operator_services os ON os.service_id = s.id
                   WHERE os.operator_id = $1 AND s.is_active
                   ORDER BY s.sort_order, s.id""",
                operator["id"],
            )
        return [r["id"] for r in rows]

    async def get_operator_flag_ids(self, op_id: int) -> list[int]:
        """Именно проставленные флаги — без раскрытия админской привилегии
        (админу их тоже показываем и даём редактировать)."""
        rows = await self.pool.fetch(
            "SELECT service_id FROM operator_services WHERE operator_id=$1", op_id
        )
        return [r["service_id"] for r in rows]

    async def set_operator_services(self, op_id: int, service_ids: list[int]) -> list[int]:
        """Переписать флаги доступа. Возвращает снятые сервисы — по ним нужно
        вернуть тикеты оператора в очередь."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                before = {r["service_id"] for r in await conn.fetch(
                    "SELECT service_id FROM operator_services WHERE operator_id=$1", op_id
                )}
                await conn.execute("DELETE FROM operator_services WHERE operator_id=$1", op_id)
                if service_ids:
                    await conn.executemany(
                        "INSERT INTO operator_services (operator_id, service_id) VALUES ($1,$2) "
                        "ON CONFLICT DO NOTHING",
                        [(op_id, sid) for sid in service_ids],
                    )
                return sorted(before - set(service_ids))

    async def get_service_counts(self, service_ids: list[int]) -> dict[int, int]:
        """Счётчик на пилюле сервиса: «новые + непрочитанные» — открытые тикеты,
        которые ждут внимания (в очереди либо с непрочитанными сообщениями)."""
        if not service_ids:
            return {}
        rows = await self.pool.fetch(
            """SELECT service_id, COUNT(*) AS cnt FROM dialogs
               WHERE service_id = ANY($1::int[]) AND status <> 'closed'
                 AND (unread_count > 0 OR status = 'queue')
               GROUP BY service_id""",
            service_ids,
        )
        counts = {sid: 0 for sid in service_ids}
        counts.update({r["service_id"]: int(r["cnt"]) for r in rows})
        return counts

    # ── Dialogs ───────────────────────────────────────────────────────────────

    async def upsert_dialog(
        self, dialog_id: str, chat_id: str, service_id: int,
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
                status, queued_at, service_id
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13, 1,
                      CASE WHEN $3 THEN 'ai' ELSE 'queue' END,
                      CASE WHEN $3 THEN NULL ELSE NOW() END, $14)
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
            ui.get("user_photo_url"), service_id,
        )
        return {**dict(row), "is_new_dialog": is_new or was_closed}

    # Диалог всегда читается вместе с данными своего сервиса: слаг нужен для
    # синхронизации с n8n и ключей Redis, имя и цвет — фронту, чтобы в режиме
    # «Все сервисы» было видно, чей это тикет.
    _DIALOG_SELECT = """
        SELECT d.*, s.slug AS service_slug, s.name AS service_name,
               s.color AS service_color, s.emoji AS service_emoji,
               s.qdrant_collection, s.n8n_webhook_url,
               s.business_connection_id
        FROM dialogs d JOIN services s ON s.id = d.service_id
    """

    async def get_all_dialogs(self, service_ids: list[int]) -> list[dict]:
        rows = await self.pool.fetch(
            f"{self._DIALOG_SELECT} WHERE d.service_id = ANY($1::int[]) ORDER BY d.updated_at DESC",
            service_ids,
        )
        return [dict(r) for r in rows]

    async def get_dialog(self, dialog_id: str) -> Optional[dict]:
        row = await self.pool.fetchrow(
            f"{self._DIALOG_SELECT} WHERE d.dialog_id = $1", dialog_id
        )
        return dict(row) if row else None

    # chat_id — это Telegram user_id, он уникален у пользователя, но НЕ между
    # сервисами: один человек может писать в боты двух ВПН-ов. Поэтому поиск
    # активного диалога и истории всегда идёт по паре (сервис, chat_id).

    async def get_active_dialog_by_chat_id(
        self, service_id: int, chat_id: str, exclude_dialog_id: str = "",
    ) -> Optional[dict]:
        row = await self.pool.fetchrow(
            f"{self._DIALOG_SELECT} WHERE d.service_id=$1 AND d.chat_id=$2 "
            f"AND d.status != 'closed' AND d.dialog_id != $3 LIMIT 1",
            service_id, chat_id, exclude_dialog_id,
        )
        return dict(row) if row else None

    async def get_dialog_history(
        self, service_id: int, chat_id: str, exclude_dialog_id: str = "",
    ) -> list[dict]:
        rows = await self.pool.fetch(
            """SELECT dialog_id, last_message_text, summary, status, updated_at, rating
               FROM dialogs WHERE service_id=$1 AND chat_id=$2 AND status='closed' AND dialog_id!=$3
               ORDER BY updated_at DESC LIMIT 10""",
            service_id, chat_id, exclude_dialog_id,
        )
        return [dict(r) for r in rows]

    async def update_last_message(self, dialog_id: str, text: str):
        await self.pool.execute(
            "UPDATE dialogs SET last_message_text=$1, last_message_time=NOW(), updated_at=NOW() WHERE dialog_id=$2",
            text, dialog_id,
        )

    async def update_ai_enabled(self, dialog_id: str, ai_enabled: bool):
        await self.pool.execute(
            "UPDATE dialogs SET ai_enabled=$1, updated_at=NOW() WHERE dialog_id=$2",
            ai_enabled, dialog_id,
        )

    # n8n_dialogs общая с воркфлоу n8n; строки разделены колонкой service —
    # без неё переключение ИИ в одном ВПН-е гасило бы бота в другом у того же
    # Telegram-пользователя.

    @staticmethod
    def _n8n_keys(dialog: dict) -> list[str]:
        """Чем n8n метит свои строки в колонке `service`. Один воркфлоу на все
        сервисы метит их business_connection_id, отдельный воркфлоу на сервис —
        слагом. Сверяем по обоим, чтобы синхронизация работала при любом из
        вариантов и не ломалась на переходе между ними."""
        return [v for v in (dialog.get("service_slug"),
                            dialog.get("business_connection_id")) if v]

    async def sync_n8n_dialog_status(self, chat_id: str, status: str, dialog: dict):
        try:
            await self.pool.execute(
                "UPDATE n8n_dialogs SET status=$1 WHERE id=("
                "  SELECT MAX(id) FROM n8n_dialogs WHERE user_id=$2 AND service = ANY($3::text[]))",
                status, int(chat_id), self._n8n_keys(dialog),
            )
        except Exception as e:
            print(f"[sync_n8n] status update error: {e}")

    async def sync_n8n_dialog_ai_status(self, chat_id: str, ai_enabled: bool, dialog: dict):
        try:
            await self.pool.execute(
                "UPDATE n8n_dialogs SET ai_status=$1 WHERE user_id=$2 AND service = ANY($3::text[])",
                ai_enabled, int(chat_id), self._n8n_keys(dialog),
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

    # service_id=None → глобальная настройка (звуки, флаги миграций).
    # Контентные настройки (ai_settings / automation / schedule) всегда
    # запрашиваются с конкретным service_id.

    async def get_setting(self, key: str, service_id: int = None) -> Optional[str]:
        row = await self.pool.fetchrow(
            "SELECT value FROM settings WHERE key=$1 AND service_id=$2",
            key, service_id or GLOBAL_SERVICE_ID,
        )
        return row["value"] if row else None

    async def set_setting(self, key: str, value: str, service_id: int = None):
        await self.pool.execute(
            "INSERT INTO settings (key,value,service_id) VALUES ($1,$2,$3) "
            "ON CONFLICT (key, service_id) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()",
            key, value, service_id or GLOBAL_SERVICE_ID,
        )

    async def get_setting_json(self, key: str, default=None, service_id: int = None):
        val = await self.get_setting(key, service_id)
        return json.loads(val) if val else default

    async def set_setting_json(self, key: str, value, service_id: int = None):
        await self.set_setting(key, json.dumps(value, ensure_ascii=False), service_id)

    # ── Stats ─────────────────────────────────────────────────────────────────

    async def get_stats(self, days: int = 14, service_ids: list[int] = None) -> dict:
        sids = service_ids or []
        today_total = await self.pool.fetchval(
            "SELECT COUNT(*) FROM dialogs "
            "WHERE service_id = ANY($1::int[]) AND created_at::date = CURRENT_DATE", sids
        ) or 0
        today_closed = await self.pool.fetchval(
            "SELECT COUNT(*) FROM dialogs WHERE service_id = ANY($1::int[]) "
            "AND status='closed' AND updated_at::date = CURRENT_DATE", sids
        ) or 0
        ai_resolved = await self.pool.fetchval(
            "SELECT COUNT(*) FROM dialogs WHERE service_id = ANY($1::int[]) "
            "AND status='closed' AND operator_called=FALSE AND updated_at::date = CURRENT_DATE", sids
        ) or 0
        ai_pct = int(ai_resolved / today_closed * 100) if today_closed else 0

        # Daily counts for last N days (missing days filled with 0)
        daily_rows = await self.pool.fetch(
            """SELECT created_at::date as d, COUNT(*) as cnt
               FROM dialogs WHERE service_id = ANY($2::int[])
                 AND created_at >= NOW() - ($1 || ' days')::interval
               GROUP BY d ORDER BY d""",
            str(days), sids,
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
               FROM dialogs WHERE service_id = ANY($1::int[])
                 AND created_at >= NOW() - '14 days'::interval
               GROUP BY h ORDER BY h""",
            sids,
        )
        hourly_map = {r["h"]: r["cnt"] for r in hourly_rows}
        hourly = [int(hourly_map.get(h, 0)) for h in range(24)]

        # Operator performance
        op_rows = await self.pool.fetch("SELECT * FROM operators ORDER BY id")
        operators = []
        for op in op_rows:
            closed = await self.pool.fetchval(
                "SELECT COUNT(*) FROM dialogs WHERE service_id = ANY($1::int[]) "
                "AND status='closed' AND updated_at::date = CURRENT_DATE", sids
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
            "top_questions": await self._get_top_questions(sids),
        }

    async def _get_top_questions(self, service_ids: list[int]) -> list[dict]:
        rows = await self.pool.fetch(
            """SELECT m.category AS q, COUNT(*) AS count
               FROM messages m
               JOIN dialogs d ON d.dialog_id = m.dialog_id
               WHERE d.service_id = ANY($1::int[])
                 AND m.kind='user' AND m.category IS NOT NULL
                 AND m.created_at >= NOW() - '30 days'::interval
               GROUP BY m.category ORDER BY count DESC LIMIT 10""",
            service_ids,
        )
        return [{"q": r["q"], "count": r["count"]} for r in rows]

    async def get_time_stats(self, days: int = 30, service_ids: list[int] = None) -> dict:
        interval = timedelta(days=days)
        sids = service_ids or []

        team_first = await self.pool.fetchval("""
            SELECT AVG(EXTRACT(EPOCH FROM (m.created_at - d.created_at)))
            FROM dialogs d
            JOIN LATERAL (
                SELECT created_at, operator_name FROM messages
                WHERE dialog_id = d.dialog_id AND kind = 'operator'
                ORDER BY created_at ASC LIMIT 1
            ) m ON true
            WHERE d.created_at >= NOW() - $1::interval
              AND d.service_id = ANY($2::int[])
        """, interval, sids)

        team_next = await self.pool.fetchval("""
            SELECT AVG(EXTRACT(EPOCH FROM (m_op.created_at - m_usr.created_at)))
            FROM messages m_op
            JOIN dialogs d ON d.dialog_id = m_op.dialog_id
            JOIN LATERAL (
                SELECT created_at FROM messages
                WHERE dialog_id = m_op.dialog_id AND kind = 'user'
                  AND created_at < m_op.created_at
                ORDER BY created_at DESC LIMIT 1
            ) m_usr ON true
            WHERE m_op.kind = 'operator'
              AND m_op.created_at >= NOW() - $1::interval
              AND d.service_id = ANY($2::int[])
        """, interval, sids)

        team_close = await self.pool.fetchval("""
            SELECT AVG(EXTRACT(EPOCH FROM (closed_at - created_at)))
            FROM dialogs
            WHERE status = 'closed' AND closed_at IS NOT NULL
              AND created_at >= NOW() - $1::interval
              AND service_id = ANY($2::int[])
        """, interval, sids)

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
              AND d.service_id = ANY($2::int[])
            GROUP BY m.operator_name
        """, interval, sids)

        op_next_rows = await self.pool.fetch("""
            SELECT m_op.operator_name,
                   AVG(EXTRACT(EPOCH FROM (m_op.created_at - m_usr.created_at))) AS avg_sec
            FROM messages m_op
            JOIN dialogs d ON d.dialog_id = m_op.dialog_id
            JOIN LATERAL (
                SELECT created_at FROM messages
                WHERE dialog_id = m_op.dialog_id AND kind = 'user'
                  AND created_at < m_op.created_at
                ORDER BY created_at DESC LIMIT 1
            ) m_usr ON true
            WHERE m_op.kind = 'operator'
              AND m_op.created_at >= NOW() - $1::interval
              AND m_op.operator_name IS NOT NULL
              AND d.service_id = ANY($2::int[])
            GROUP BY m_op.operator_name
        """, interval, sids)

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
            "SELECT * FROM kb_articles WHERE service_id=$1 ORDER BY created_at DESC", service_id,
        )
        return [dict(r) for r in rows]

    async def delete_kb_article(self, article_id: str, service_id: int) -> bool:
        result = await self.pool.execute(
            "DELETE FROM kb_articles WHERE id=$1 AND service_id=$2", article_id, service_id,
        )
        return result == "DELETE 1"

    async def reset_kb(self, service_id: int):
        await self.pool.execute("DELETE FROM kb_articles WHERE service_id=$1", service_id)

    # service_id IS NULL у шаблона = общий для всех сервисов.
    async def get_templates(self, service_id: int) -> list[dict]:
        rows = await self.pool.fetch(
            "SELECT * FROM message_templates WHERE service_id=$1 OR service_id IS NULL "
            "ORDER BY group_name, title",
            service_id,
        )
        return [dict(r) for r in rows]

    async def save_template(
        self, id: int | None, group_name: str, title: str, text: str, service_id: int,
    ) -> dict | None:
        if id:
            row = await self.pool.fetchrow(
                "UPDATE message_templates SET group_name=$1, title=$2, text=$3 "
                "WHERE id=$4 AND (service_id=$5 OR service_id IS NULL) RETURNING *",
                group_name, title, text, id, service_id,
            )
        else:
            row = await self.pool.fetchrow(
                "INSERT INTO message_templates (group_name, title, text, service_id) "
                "VALUES ($1,$2,$3,$4) RETURNING *",
                group_name, title, text, service_id,
            )
        return dict(row) if row else None

    async def delete_template(self, template_id: int, service_id: int) -> bool:
        result = await self.pool.execute(
            "DELETE FROM message_templates WHERE id=$1 AND (service_id=$2 OR service_id IS NULL)",
            template_id, service_id,
        )
        return result == "DELETE 1"

    async def rename_template_group(self, old_name: str, new_name: str, service_id: int):
        await self.pool.execute(
            "UPDATE message_templates SET group_name=$1 "
            "WHERE group_name=$2 AND (service_id=$3 OR service_id IS NULL)",
            new_name, old_name, service_id,
        )

    async def get_user_message_count(self, dialog_id: str) -> int:
        return await self.pool.fetchval(
            "SELECT COUNT(*) FROM messages WHERE dialog_id=$1 AND kind='user'", dialog_id
        ) or 0

    async def set_dialog_rating(self, dialog_id: str, rating: int):
        await self.pool.execute(
            "UPDATE dialogs SET rating=$1 WHERE dialog_id=$2", rating, dialog_id
        )

    async def get_all_chat_ids(self, service_id: int) -> list:
        rows = await self.pool.fetch(
            "SELECT DISTINCT chat_id FROM dialogs WHERE service_id=$1 AND chat_id IS NOT NULL",
            service_id,
        )
        return [r["chat_id"] for r in rows]

    # Slot definition: only in_progress tickets occupy an operator slot.
    # Слоты считаются по паре (оператор, сервис): лимит max_tickets_per_operator
    # настраивается отдельно у каждого ВПН-а, поэтому и загрузка меряется внутри
    # сервиса. Single source of truth — каждая проверка ёмкости джойнится сюда.
    _SLOT_COUNT_SQL = """
        SELECT assigned_operator, service_id, COUNT(*) AS cnt
        FROM dialogs
        WHERE status = 'in_progress' AND assigned_operator IS NOT NULL
        GROUP BY assigned_operator, service_id
    """

    # $1 — max_tickets сервиса, $2 — сам сервис. Доступ к сервису: явный флаг в
    # operator_services либо роль admin (админ обслуживает все сервисы).
    _HAS_SERVICE_ACCESS_SQL = """
        (o.role = 'admin' OR EXISTS (
            SELECT 1 FROM operator_services os
            WHERE os.operator_id = o.id AND os.service_id = $2))
    """

    _FREE_OPERATOR_SQL = f"""
        SELECT o.name
        FROM operators o
        LEFT JOIN ({_SLOT_COUNT_SQL}) active
               ON active.assigned_operator = o.name AND active.service_id = $2
        WHERE o.online = TRUE
          AND COALESCE(o.paused, FALSE) = FALSE
          AND COALESCE(active.cnt, 0) < $1
          AND {_HAS_SERVICE_ACCESS_SQL}
        ORDER BY COALESCE(active.cnt, 0) ASC
        LIMIT 1
    """

    # Full in_progress claim state; callers that (re)bind an operator prepend
    # `assigned_operator = $1,` — pending returns keep the existing binding.
    _CLAIM_STATE_SQL = """
        status = 'in_progress',
        sla_started_at = COALESCE(sla_started_at, NOW()),
        waiting_reason = NULL,
        queued_at = NULL,
        return_requested_at = NULL,
        updated_at = NOW()
    """

    async def assign_dialog(self, dialog_id: str, max_tickets: int, service_id: int) -> str | None:
        """Hand the dialog to the least-loaded online operator with a free slot
        WHO HAS ACCESS TO THE DIALOG'S SERVICE, atomically setting the full
        in_progress state (SLA start included). Uses an advisory lock so
        concurrent claims don't exceed max_tickets."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1)", self._ASSIGN_LOCK)
                row = await conn.fetchrow(self._FREE_OPERATOR_SQL, max_tickets, service_id)
                if not row:
                    return None
                op_name = row["name"]
                await conn.execute(
                    f"UPDATE dialogs SET assigned_operator = $1, {self._CLAIM_STATE_SQL} "
                    f"WHERE dialog_id = $2",
                    op_name, dialog_id,
                )
                return op_name

    async def claim_next_queued(self, max_tickets: int, service_id: int) -> dict | None:
        """Atomically bind the oldest queued dialog OF THIS SERVICE (status='queue'
        only — never AI-handled ones) to the least-loaded online operator with
        capacity and access. Returns {'dialog': dict, 'op_name': str} or None."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1)", self._ASSIGN_LOCK)
                op_row = await conn.fetchrow(self._FREE_OPERATOR_SQL, max_tickets, service_id)
                if not op_row:
                    return None
                dialog_row = await conn.fetchrow(f"""
                    UPDATE dialogs SET assigned_operator = $1, {self._CLAIM_STATE_SQL}
                    WHERE dialog_id = (
                        SELECT dialog_id FROM dialogs
                        WHERE status = 'queue' AND service_id = $2
                        ORDER BY COALESCE(queued_at, created_at) ASC LIMIT 1
                    )
                    RETURNING *
                """, op_row["name"], service_id)
                if not dialog_row:
                    return None
                return {"dialog": dict(dialog_row), "op_name": op_row["name"]}

    async def claim_pending_return(self, max_tickets: int, service_id: int) -> dict | None:
        """Return the oldest waiting dialog of this service whose client already
        replied (return_requested_at set) to ITS OWN operator, provided that
        operator is online, still has access to the service and has a free slot.
        Ignores 'paused' — it's the operator's own ticket coming back.
        Returns {'dialog': dict, 'op_name': str} or None."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1)", self._ASSIGN_LOCK)
                dialog_row = await conn.fetchrow(f"""
                    UPDATE dialogs SET {self._CLAIM_STATE_SQL}
                    WHERE dialog_id = (
                        SELECT d.dialog_id
                        FROM dialogs d
                        JOIN operators o ON o.name = d.assigned_operator
                        LEFT JOIN ({self._SLOT_COUNT_SQL}) active
                               ON active.assigned_operator = o.name
                              AND active.service_id = d.service_id
                        WHERE d.status = 'waiting'
                          AND d.service_id = $2
                          AND d.return_requested_at IS NOT NULL
                          AND o.online = TRUE
                          AND COALESCE(active.cnt, 0) < $1
                          AND {self._HAS_SERVICE_ACCESS_SQL}
                        ORDER BY d.return_requested_at ASC
                        LIMIT 1
                    )
                    RETURNING *
                """, max_tickets, service_id)
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
            UPDATE dialogs SET assigned_operator = $1, {self._CLAIM_STATE_SQL}
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

    async def get_operator_dialogs_by_status(
        self, op_name: str, status: str, service_id: int = None,
    ) -> list[dict]:
        rows = await self.pool.fetch(
            "SELECT * FROM dialogs WHERE assigned_operator=$1 AND status=$2 "
            "AND ($3::int IS NULL OR service_id = $3)",
            op_name, status, service_id,
        )
        return [dict(r) for r in rows]

    async def get_service_ids_with_pending(self) -> list[int]:
        """Сервисы, где есть что раздавать, — от самого залежавшегося тикета.
        Раздача идёт по сервисам (у каждого свой лимит слотов и свой круг
        операторов), а такой порядок не даёт одному ВПН-у голодать."""
        rows = await self.pool.fetch("""
            SELECT service_id,
                   MIN(COALESCE(queued_at, return_requested_at, created_at)) AS oldest
            FROM dialogs
            WHERE status = 'queue'
               OR (status = 'waiting' AND return_requested_at IS NOT NULL)
            GROUP BY service_id
            ORDER BY oldest ASC
        """)
        return [r["service_id"] for r in rows]

    async def reset_operator_presence(self):
        """Startup: nobody is connected yet, so any online=TRUE row is a phantom
        left by a hard crash (the WS disconnect handler never ran). Mark them
        offline and arm the grace timer so the routing sweeper redistributes
        their tickets unless they reconnect in time."""
        await self.pool.execute(
            """UPDATE operators
               SET online=FALSE, offline_since=COALESCE(offline_since, NOW())
               WHERE COALESCE(online, FALSE) = TRUE"""
        )

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
