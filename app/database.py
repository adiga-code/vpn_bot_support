import asyncpg
from typing import Optional
from app.config import Settings


class DatabaseManager:
    """Маппинг chat_id ↔ topic_id через PostgreSQL"""

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
            CREATE TABLE IF NOT EXISTS chat_topics (
                id          SERIAL PRIMARY KEY,
                dialog_id   TEXT UNIQUE NOT NULL,
                chat_id     TEXT NOT NULL,
                topic_id    INTEGER NOT NULL,
                created_at  TIMESTAMP DEFAULT NOW()
            )
        """)
        print("✅ Database initialized (PostgreSQL)")

    async def save_chat_topic(self, dialog_id: str, chat_id: str, topic_id: int) -> None:
        await self.pool.execute("""
            INSERT INTO chat_topics (dialog_id, chat_id, topic_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (dialog_id) DO UPDATE SET
                chat_id  = EXCLUDED.chat_id,
                topic_id = EXCLUDED.topic_id
        """, dialog_id, chat_id, topic_id)

    async def get_topic_id(self, dialog_id: str) -> Optional[int]:
        row = await self.pool.fetchrow(
            "SELECT topic_id FROM chat_topics WHERE dialog_id = $1", dialog_id
        )
        return row["topic_id"] if row else None

    async def get_dialog_id_by_topic(self, topic_id: int) -> Optional[tuple[str, str]]:
        row = await self.pool.fetchrow(
            "SELECT dialog_id, chat_id FROM chat_topics WHERE topic_id = $1", topic_id
        )
        return (row["dialog_id"], row["chat_id"]) if row else None

    async def close(self):
        if self.pool:
            await self.pool.close()
