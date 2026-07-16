from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Redis (история/KV для n8n) ────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379"

    # ── RabbitMQ (очереди сообщений) ──────────────────────────────────────────
    RABBITMQ_URL: str = "amqp://guest:guest@localhost/"

    # ── n8n webhook для исходящих событий ────────────────────────────────────
    # Если задан — исходящие события (manager_message / send_to_user /
    # operator_notify / billing_action) отправляются POST-ом на этот Webhook
    # вместо очереди RabbitMQ vpn_bot.outgoing, например:
    #   N8N_WEBHOOK_URL=https://n8n.example.com/webhook/vpn-bot-outgoing
    # RabbitMQ остаётся резервным каналом: если вебхук недоступен после
    # ретраев, сообщение публикуется в очередь как раньше.
    # Запрос несёт заголовок X-API-Key: N8N_API_KEY (если N8N_API_KEY задан).
    N8N_WEBHOOK_URL: str = ""

    # ── PostgreSQL ────────────────────────────────────────────────────────────
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "vpnbot"
    POSTGRES_USER: str = "vpnbot"
    POSTGRES_PASSWORD: str

    # ── Web server ────────────────────────────────────────────────────────────
    WEB_HOST: str = "0.0.0.0"
    WEB_PORT: int = 8000

    # ── File uploads ──────────────────────────────────────────────────────────
    UPLOADS_DIR: str = "app/uploads"
    # Public base URL for absolute file links (scheme+host only, no path suffix)
    # e.g. BASE_URL=https://helpdesk.example.com
    # Required for n8n → Telegram file forwarding. Leave empty for dev/local use.
    BASE_URL: str = ""
    # Subpath prefix nginx proxies WITHOUT stripping, e.g. /files
    # If nginx passes /files/api/... to the app as-is, set BASE_URL_PATH=/files
    BASE_URL_PATH: str = ""
    # Static API key for n8n file uploads — set any random string, e.g.:
    # python -c "import secrets; print(secrets.token_hex(24))"
    N8N_API_KEY: str = ""

    # ── S3-compatible storage (optional) ──────────────────────────────────────
    # If S3_BUCKET + S3_ACCESS_KEY are set, S3 is used instead of local disk.
    # Compatible with AWS S3, Cloudflare R2, MinIO, Yandex Object Storage, etc.
    S3_BUCKET:       str = ""
    S3_ENDPOINT_URL: str = ""   # e.g. https://s3.amazonaws.com or MinIO URL
    S3_ACCESS_KEY:   str = ""
    S3_SECRET_KEY:   str = ""
    S3_REGION:       str = "us-east-1"
    S3_PUBLIC_URL:   str = ""   # CDN / custom domain override for public file URLs

    # ── Auth ──────────────────────────────────────────────────────────────────
    # Required — generate with: python -c "import secrets; print(secrets.token_hex(32))"
    SECRET_KEY: str
    # Optional — if set and no operators exist, creates the first admin on startup
    ADMIN_INIT_TG: str = ""
    ADMIN_INIT_PASSWORD: str = ""

    # ── AI providers ─────────────────────────────────────────────────────────
    # CHAT_PROVIDER selects the LLM for classification and KB chunking.
    # "openai" (default) uses OPENAI_API_KEY with gpt-4o-mini.
    # "gemini" uses GEMINI_API_KEY with gemini-2.0-flash via OpenAI-compat API.
    # Embeddings always use OpenAI (OPENAI_API_KEY required for KB upload).
    CHAT_PROVIDER: str = "openai"
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # ── Qdrant ────────────────────────────────────────────────────────────────
    QDRANT_URL: str = "http://qdrant:6333"

    # ── Billing API ───────────────────────────────────────────────────────────
    # Leave empty to fall back to StubBillingProvider
    BILLING_API_URL: str = ""
    BILLING_API_TOKEN: str = ""

    # ── Server monitoring ─────────────────────────────────────────────────────
    # SERVERS_MONITOR_TYPE: "tcp" | "http" | "stub"
    # SERVERS: JSON list of servers, e.g.
    #   '[{"name":"Frankfurt-01","host":"1.2.3.4","port":443,"location":"DE"}]'
    SERVERS_MONITOR_TYPE: str = "stub"
    SERVERS: str = "[]"
    SERVERS_CHECK_INTERVAL: int = 300  # seconds
    SERVERS_HEALTH_PATH: str = "/health"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def uploads_path(self) -> Path:
        p = Path(self.UPLOADS_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p
