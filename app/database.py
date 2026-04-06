import asyncpg
from typing import Optional


class DatabaseManager:
    """Маппинг chat_id ↔ topic_id через PostgreSQL"""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: asyncpg.Pool = None

    async def init_db(self):
        self.pool = await asyncpg.create_pool(self.dsn)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS chat_topics (
                id         SERIAL PRIMARY KEY,
                chat_id    TEXT UNIQUE NOT NULL,
                topic_id   INTEGER NOT NULL,
                topic_name TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        print("✅ Database initialized (PostgreSQL)")

    async def save_chat_topic(self, chat_id: str, topic_id: int, topic_name: str) -> None:
        await self.pool.execute("""
            INSERT INTO chat_topics (chat_id, topic_id, topic_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (chat_id) DO UPDATE SET
                topic_id   = EXCLUDED.topic_id,
                topic_name = EXCLUDED.topic_name
        """, chat_id, topic_id, topic_name)

    async def get_topic_id(self, chat_id: str) -> Optional[int]:
        row = await self.pool.fetchrow(
            "SELECT topic_id FROM chat_topics WHERE chat_id = $1", chat_id
        )
        return row["topic_id"] if row else None

    async def get_chat_id_by_topic(self, topic_id: int) -> Optional[str]:
        row = await self.pool.fetchrow(
            "SELECT chat_id FROM chat_topics WHERE topic_id = $1", topic_id
        )
        return row["chat_id"] if row else None

    async def close(self):
        if self.pool:
            await self.pool.close()
