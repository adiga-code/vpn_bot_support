from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Настройки приложения из .env"""

    # Telegram
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_GROUP_ID: int

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # PostgreSQL
    POSTGRES_URL: str

    # Custom Emoji IDs для иконок топиков
    ICON_AI_ENABLED: str = "5417915203100613993"
    ICON_AI_DISABLED: str = "5237699328843200968"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"