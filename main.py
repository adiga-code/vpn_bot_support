import asyncio
import uvicorn
import redis.asyncio as aioredis

from app.config import Settings
from app.database import DatabaseManager
from app.ws_manager import WebSocketManager
from app.n8n_client import N8NClient
from app.billing import make_billing_provider
from app.web_server import build_app
from app.redis_consumer import RedisConsumer


async def main():
    settings = Settings()

    db = DatabaseManager(settings)
    await db.init_db()

    redis = aioredis.from_url(settings.REDIS_URL)
    ws_manager = WebSocketManager()
    n8n_client = N8NClient(settings, redis)
    billing = make_billing_provider(settings.BILLING_API_URL, settings.BILLING_API_TOKEN)
    consumer = RedisConsumer(redis, db, ws_manager)

    app = build_app(settings, db, ws_manager, n8n_client, billing)

    config = uvicorn.Config(
        app,
        host=settings.WEB_HOST,
        port=settings.WEB_PORT,
        log_level="info",
    )
    server = uvicorn.Server(config)

    print(f"✅ Helpdesk starting on http://{settings.WEB_HOST}:{settings.WEB_PORT}")

    try:
        await asyncio.gather(
            server.serve(),
            consumer.consume(),
        )
    finally:
        await redis.aclose()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
