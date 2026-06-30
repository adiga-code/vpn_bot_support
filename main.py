import asyncio
import json

import aio_pika
import uvicorn
import redis.asyncio as aioredis

from app.ai_client import make_chat_client
from app.auth import hash_password
from app.billing import make_billing_provider
from app.config import Settings
from app.database import DatabaseManager
from app.n8n_client import N8NClient
from app.rabbitmq_consumer import RabbitMQConsumer
from app.servers import make_server_monitor
from app.web_server import build_app
from app.ws_manager import WebSocketManager


async def main():
    # ── Bootstrap ─────────────────────────────────────────────────────────────
    settings = Settings()

    db = DatabaseManager(settings)
    await db.init_db()

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

    # ── Server-down notification callback ─────────────────────────────────────
    async def on_server_down(name: str, location: str):
        await n8n_client.schedule_notify("server_down", {"server_name": name, "location": location})
        print(f"[NOTIF] server_down: {name} ({location})")

    server_monitor = make_server_monitor(
        monitor_type=settings.SERVERS_MONITOR_TYPE,
        servers=json.loads(settings.SERVERS),
        interval=settings.SERVERS_CHECK_INTERVAL,
        health_path=settings.SERVERS_HEALTH_PATH,
        on_server_down=on_server_down,
    )

    chat_client = make_chat_client(settings.CHAT_PROVIDER, settings.OPENAI_API_KEY, settings.GEMINI_API_KEY)
    consumer = RabbitMQConsumer(rmq, db, ws_manager, n8n_client, chat_client)
    app = build_app(settings, db, ws_manager, n8n_client, billing, server_monitor)

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
            server_monitor.run_forever(),
        )
    finally:
        await rmq.close()
        await redis.aclose()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
