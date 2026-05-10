from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Настройки приложения из .env"""

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
