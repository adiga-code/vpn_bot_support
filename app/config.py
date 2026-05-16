from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # PostgreSQL
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "vpnbot"
    POSTGRES_USER: str = "vpnbot"
    POSTGRES_PASSWORD: str

    # Web server
    WEB_HOST: str = "0.0.0.0"
    WEB_PORT: int = 8000

    # File uploads directory
    UPLOADS_DIR: str = "app/uploads"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def uploads_path(self) -> Path:
        p = Path(self.UPLOADS_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p
