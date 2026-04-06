import asyncio
import redis.asyncio as aioredis
from app.config import Settings
from app.database import DatabaseManager
from app.telegram_bot import TelegramBot
from app.redis_consumer import RedisConsumer


async def main():
    settings = Settings()

    db = DatabaseManager(settings.POSTGRES_URL)
    await db.init_db()

    redis = aioredis.from_url(settings.REDIS_URL)

    telegram_bot = TelegramBot(settings, db, redis)
    consumer = RedisConsumer(redis, telegram_bot)

    await telegram_bot.start()
    await consumer.start()

    print("✅ Bot running")

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await consumer.stop()
        await telegram_bot.stop()
        await redis.aclose()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
