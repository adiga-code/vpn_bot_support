import asyncio

import aio_pika
import uvicorn
import redis.asyncio as aioredis

from app.ai_client import make_chat_client
from app.auth import hash_password
from app.billing import make_billing_provider
from app.config import Settings
from app.database import DatabaseManager
from app.health import ServiceHealthMonitor
from app.n8n_client import N8NClient
from app.rabbitmq_consumer import RabbitMQConsumer
from app.routing import RoutingEngine
from app.web_server import build_app
from app.ws_manager import WebSocketManager

# Импорт ради регистрации провайдеров мониторинга в реестре app.health.
# Свой источник данных подключается таким же импортом — см. README.
import app.bots  # noqa: F401
import app.servers  # noqa: F401


async def main():
    # ── Bootstrap ─────────────────────────────────────────────────────────────
    settings = Settings()

    db = DatabaseManager(settings)
    await db.init_db()
    # A hard crash skips WS disconnect handlers — clear phantom online flags
    # and arm the offline grace so stuck tickets get redistributed.
    await db.reset_operator_presence()

    # ── Initial admin account ─────────────────────────────────────────────────
    if settings.ADMIN_INIT_TG and settings.ADMIN_INIT_PASSWORD:
        pw_hash = hash_password(settings.ADMIN_INIT_PASSWORD)
        existing = await db.get_operator_by_tg(settings.ADMIN_INIT_TG)
        if existing:
            if not existing.get("password_hash"):
                await db.set_password(existing["id"], pw_hash)
                print(f"[AUTH] Password set for operator: {settings.ADMIN_INIT_TG}")
        else:
            op = await db.create_operator("Admin", settings.ADMIN_INIT_TG, "admin")
            await db.set_password(op["id"], pw_hash)
            print(f"[AUTH] Admin created: {settings.ADMIN_INIT_TG}")

    # ── Print login credentials ───────────────────────────────────────────────
    ops = await db.get_operators()
    print("=" * 50)
    print("  HELPDESK LOGIN CREDENTIALS")
    print("=" * 50)
    if ops:
        for op in ops:
            has_pw = "✓ password set" if op.get("password_hash") else "✗ NO PASSWORD — set ADMIN_INIT_PASSWORD"
            print(f"  [{op['role'].upper()}] {op['tg']}  ({has_pw})")
        if settings.ADMIN_INIT_TG and settings.ADMIN_INIT_PASSWORD:
            print(f"\n  Active credentials:")
            print(f"  Login:    {settings.ADMIN_INIT_TG}")
            print(f"  Password: {settings.ADMIN_INIT_PASSWORD}")
    else:
        print("  No operators found.")
        print("  Set ADMIN_INIT_TG and ADMIN_INIT_PASSWORD in .env")
    print("=" * 50)

    redis = aioredis.from_url(settings.REDIS_URL)
    rmq = await aio_pika.connect_robust(settings.RABBITMQ_URL)

    ws_manager = WebSocketManager()
    n8n_client = N8NClient(settings, rmq, redis, db)
    billing = make_billing_provider(settings.BILLING_API_URL, settings.BILLING_API_TOKEN)

    # ── Уведомление о падении сервера или бота ────────────────────────────────
    # Уходит боту того ВПН-а, чей компонент лёг, а не всем подряд.
    async def on_component_down(service: dict, component: dict):
        event = "bot_down" if component.get("kind") == "bots" else "server_down"
        await n8n_client.schedule_notify(event, {
            "server_name": component.get("name"),
            "location": component.get("location", ""),
            "reason": component.get("message", ""),
            "service_name": service.get("name"),
        }, service)
        print(f"[NOTIF] {event}: {component.get('name')} ({service.get('slug')})")

    health_monitor = ServiceHealthMonitor(db, on_component_down=on_component_down)

    chat_client = make_chat_client(settings.CHAT_PROVIDER, settings.OPENAI_API_KEY, settings.GEMINI_API_KEY)
    routing = RoutingEngine(db, ws_manager, n8n_client)
    consumer = RabbitMQConsumer(rmq, db, ws_manager, n8n_client, routing, chat_client)
    app = build_app(settings, db, ws_manager, n8n_client, routing, billing, health_monitor)

    # ── HTTP server ───────────────────────────────────────────────────────────
    config = uvicorn.Config(
        app,
        host=settings.WEB_HOST,
        port=settings.WEB_PORT,
        log_level="info",
    )
    server = uvicorn.Server(config)

    print(f"Helpdesk starting on http://{settings.WEB_HOST}:{settings.WEB_PORT}")

    try:
        await asyncio.gather(
            server.serve(),
            consumer.consume(),
            health_monitor.run_forever(),
            routing.sweep_forever(),
        )
    finally:
        await rmq.close()
        await redis.aclose()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
