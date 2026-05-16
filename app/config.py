from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379"

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

    # ── Auth ──────────────────────────────────────────────────────────────────
    # Required — generate with: python -c "import secrets; print(secrets.token_hex(32))"
    SECRET_KEY: str
    # Optional — if set and no operators exist, creates the first admin on startup
    ADMIN_INIT_TG: str = ""
    ADMIN_INIT_PASSWORD: str = ""

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
