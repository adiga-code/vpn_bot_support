import asyncio
import uvicorn
import redis.asyncio as aioredis

from app.config import Settings
from app.database import DatabaseManager
from app.ws_manager import WebSocketManager
from app.n8n_client import N8NClient
from app.billing import make_billing_provider
from app.servers import make_server_monitor
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

    import json
    server_monitor = make_server_monitor(
        monitor_type=settings.SERVERS_MONITOR_TYPE,
        servers=json.loads(settings.SERVERS),
        interval=settings.SERVERS_CHECK_INTERVAL,
        health_path=settings.SERVERS_HEALTH_PATH,
    )

    consumer = RedisConsumer(redis, db, ws_manager)
    app = build_app(settings, db, ws_manager, n8n_client, billing, server_monitor)

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
            server_monitor.run_forever(),
        )
    finally:
        await redis.aclose()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
