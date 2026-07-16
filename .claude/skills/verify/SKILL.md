# Verify: запуск и e2e-проверка хелпдеска

Как поднять приложение и прогнать сценарии маршрутизации тикетов без полного docker-compose.

## Инфраструктура (Docker Hub может быть заблокирован — использовать mirror.gcr.io)

```bash
docker run -d --name vt-pg -e POSTGRES_DB=vpnbot -e POSTGRES_USER=vpnbot -e POSTGRES_PASSWORD=vpnbot -p 15432:5432 mirror.gcr.io/library/postgres:16-alpine
docker run -d --name vt-redis -p 16379:6379 mirror.gcr.io/library/redis:7-alpine
docker run -d --name vt-rmq -e RABBITMQ_DEFAULT_USER=vpnbot -e RABBITMQ_DEFAULT_PASS=vpnbot -p 15673:5672 mirror.gcr.io/library/rabbitmq:3-alpine
```

## Приложение

```bash
pip install --ignore-installed -r requirements.txt   # --ignore-installed из-за debian-пакетов (PyJWT/cffi)
env POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=15432 POSTGRES_DB=vpnbot POSTGRES_USER=vpnbot \
    POSTGRES_PASSWORD=vpnbot REDIS_URL=redis://127.0.0.1:16379 \
    RABBITMQ_URL=amqp://vpnbot:vpnbot@127.0.0.1:15673/ SECRET_KEY=testsecret \
    ADMIN_INIT_TG=@admin ADMIN_INIT_PASSWORD=admin123 WEB_HOST=127.0.0.1 python3 main.py
```

## Драйв сценариев

- Логин: `POST /api/auth/login {"tg":"@admin","password":"admin123"}` → token.
- Оператор «онлайн» = живой WebSocket `ws://127.0.0.1:8000/ws?token=...`. Держать клиентом на aiohttp;
  НЕ отменять `ws.receive()` через `asyncio.wait_for` — aiohttp рвёт соединение; читать через `async for`.
- Входящие от клиента/ИИ: publish JSON в очередь RabbitMQ `vpn_bot.incoming` (aio_pika):
  `{"type":"user_message","dialog_id":"d1","chat_id":"111","message":"...","ai_enabled":true}`,
  `{"type":"ai_response","dialog_id":"d1","message":"[HANDOFF] ..."}`.
- Внимание: PUT `/api/settings/automation` с `auto_handoff_enabled:false` ВЫКЛЮЧАЕТ
  `ai_settings.handoff_enabled` — для теста хендоффа слать `true`.
- Удобные настройки для теста слотов/грейса: `max_tickets_per_operator:1`, `offline_grace_seconds:15`.
- Состояние смотреть через `GET /api/dialogs` (поля status/assignedOperator/waitingReason/slaSeconds/slaStartedAt/returnRequested)
  и psql на 15432.

## GUI-скриншоты (Playwright)

CDN (unpkg/tailwind) может быть заблокирован прокси: качать пакеты с registry.npmjs.org
(react/react-dom umd, @babel/standalone, tailwindcss-cdn) и подставлять через `page.route`,
вырезая из HTML атрибуты `integrity`/`crossorigin`. Chromium: `/opt/pw-browsers/chromium`.
