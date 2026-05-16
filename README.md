# VPN Helpdesk — веб-панель техподдержки

Веб-интерфейс для операторов техподдержки VPN-сервиса. Заменяет старый интерфейс на основе Telegram-топиков.

---

## Архитектура

```
Пользователь (Telegram)
        │
        ▼
    n8n webhook
        │  (AI воркфлоу, обработка сообщений)
        ▼
      Redis ──────────────────────────────────────────────┐
        │                                                  │
        ▼                                                  ▼
  Python (FastAPI)                              vpn_bot:servers
  ├── REST API                                  (статус серверов)
  ├── WebSocket (реал-тайм)
  ├── PostgreSQL (диалоги, сообщения, операторы)
  └── Billing API (прямые вызовы)
        │
        ▼
  Браузер оператора (React SPA)
```

---

## Что делает Python, что делает n8n

### Python (этот репозиторий)

| Функция | Как реализовано |
|---|---|
| Веб-панель операторов | FastAPI + React SPA |
| Хранение диалогов и сообщений | Прямые запросы к PostgreSQL |
| Реал-тайм обновления | WebSocket broadcast |
| Управление операторами | CRUD через REST API |
| AI-настройки и расписание | PostgreSQL + публикация в Redis для n8n |
| Статистика | SQL-запросы напрямую |
| Загрузка файлов | Эндпоинт `/api/upload`, хранение на диске |
| Биллинг (продлить, трафик, ключ) | Прямой вызов внешнего API через `BillingProvider` |
| Статусы VPN-серверов | Чтение Redis-ключа `vpn_bot:servers` |

### n8n (внешний, не в этом репо)

| Функция | Почему в n8n |
|---|---|
| Приём Telegram-вебхука | Telegram API-интеграция |
| AI воркфлоу (LLM + RAG) | Визуальное редактирование без деплоя |
| Отправка сообщений пользователю | Telegram Bot API |
| Мониторинг серверов (cron) | Простой cron + Redis SET |

---

## Структура проекта

```
vpn_bot_support/
├── app/
│   ├── billing.py          # Биллинг-провайдеры (OOP, легко заменить)
│   ├── config.py           # Все настройки (читает .env)
│   ├── database.py         # PostgreSQL: схема + миграции
│   ├── n8n_client.py       # Отправка сообщений в Telegram через n8n/Redis
│   ├── redis_consumer.py   # Чтение входящих сообщений из Redis
│   ├── web_server.py       # FastAPI: все REST-эндпоинты + WebSocket
│   ├── ws_manager.py       # WebSocket broadcast менеджер
│   └── static/             # React SPA (без сборщика)
│       ├── index.html      # App + TopBar
│       ├── components.jsx  # Avatar, Icon, Toast, Badge
│       ├── dialogs.jsx     # Экран диалогов
│       ├── statistics.jsx  # Экран статистики
│       ├── servers.jsx     # Экран серверов VPN
│       └── settings.jsx    # Операторы, расписание, AI-настройки
├── main.py                 # Точка входа
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env                    # Создать из .env.example
└── .env.example
```

---

## Быстрый старт

```bash
git clone <repo>
cd vpn_bot_support

cp .env.example .env
# Заполнить .env (минимум POSTGRES_PASSWORD)

docker compose up -d --build
# Панель: http://localhost:8000
```

> После `git pull` всегда делай `docker compose up -d --build` —
> статические файлы копируются в образ при сборке.

---

## Переменные окружения (.env)

| Переменная | Обязательная | По умолчанию | Описание |
|---|---|---|---|
| `POSTGRES_PASSWORD` | ✅ | — | Пароль PostgreSQL |
| `REDIS_URL` | — | `redis://redis:6379` | URL Redis |
| `POSTGRES_HOST` | — | `postgres` | Хост PostgreSQL |
| `POSTGRES_PORT` | — | `5432` | Порт PostgreSQL |
| `POSTGRES_DB` | — | `vpnbot` | Имя базы данных |
| `POSTGRES_USER` | — | `vpnbot` | Пользователь PostgreSQL |
| `WEB_HOST` | — | `0.0.0.0` | Хост веб-сервера |
| `WEB_PORT` | — | `8000` | Порт веб-сервера |
| `BILLING_API_URL` | — | *(пусто)* | URL биллингового API |
| `BILLING_API_TOKEN` | — | *(пусто)* | Bearer-токен биллингового API |

Если `BILLING_API_URL` не задан — биллинг работает в режиме заглушки (логирует вызовы, ничего не делает).

---

## База данных

`init_db()` запускается при каждом старте и безопасен для повторного запуска:

- **Свежая установка** — создаёт все таблицы
- **Обновление** — добавляет новые колонки через `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
- **Миграция со старой системы** (Telegram-топики) — старые таблицы `dialogs`, `messages`, `chat_topics` автоматически переименуются в `*_legacy`, новые создадутся рядом

### Таблицы

**`dialogs`** — один диалог = одно обращение пользователя:
```
dialog_id           TEXT PK   — уникальный ID из n8n
chat_id             TEXT      — Telegram user ID
status              TEXT      — new | in_progress | closed
ai_enabled          BOOL      — включён ли AI
operator_called     BOOL      — пользователь позвал оператора
unread_count        INT       — счётчик непрочитанных
user_name/username  TEXT      — имя и @username
user_plan           TEXT      — тариф: Basic / Pro / ...
user_sub_status     TEXT      — active | expired | ...
user_next_payment   TEXT      — дата следующего платежа
user_traffic_used/total FLOAT — использованный и общий трафик (ГБ)
last_payment_amount/date TEXT — последний платёж
last_message_text   TEXT      — превью последнего сообщения
```

**`messages`** — сообщения в диалоге:
```
dialog_id     TEXT  — ссылка на dialogs
kind          TEXT  — user | ai | operator | system
text          TEXT  — текст сообщения
file_id       TEXT  — Telegram file_id (для справки)
file_type     TEXT  — photo | document | voice
file_url      TEXT  — URL файла на сервере (/api/files/...)
operator_name TEXT  — имя оператора если kind=operator
```

**`operators`** — учётные записи операторов:
```
name, tg, role (admin|agent), online, initials, color
```

**`settings`** — ключ-значение для настроек:
```
key=ai_settings   → JSON с prompt, temperature, auto_reply, handoff_enabled
key=schedule      → JSON расписание по дням недели
```

---

## Redis-интеграция с n8n

### n8n → Python: входящие сообщения (`LPUSH vpn_bot:incoming`)

**Сообщение пользователя:**
```json
{
  "type": "user_message",
  "dialog_id": "42",
  "chat_id": "123456789",
  "message": "Привет",
  "file_url": "/api/files/abc.jpg",
  "file_type": "photo",
  "ai_enabled": true,
  "user_name": "Иван Иванов",
  "user_username": "@ivan",
  "user_plan": "Pro",
  "user_sub_status": "active",
  "user_next_payment": "2025-06-01",
  "user_traffic_used": 45.2,
  "user_traffic_total": 100
}
```

**Ответ AI:**
```json
{
  "type": "ai_response",
  "dialog_id": "42",
  "message": "Попробуйте переподключиться"
}
```

### Python → n8n: исходящие сообщения (`PUBLISH vpn_bot:messages`)

```json
{
  "type": "manager_message",
  "dialog_id": "42",
  "chat_id": "123456789",
  "message": "Сейчас проверим",
  "file_url": "/api/files/instruction.pdf",
  "file_type": "document"
}
```

### Toggle AI (`PUBLISH vpn_bot:toggle_request` → `BLPOP vpn_bot:toggle:{dialog_id}`)

Python публикует запрос, ждёт ответ от n8n 10 секунд:
```json
// запрос
{ "type": "toggle_ai", "dialog_id": "42", "chat_id": "123456789" }

// ответ от n8n (LPUSH vpn_bot:toggle:42)
{ "ai_enabled": false }
```

### AI-настройки и расписание (Redis SET-ключи, читает n8n)

При сохранении через веб-панель Python пишет:
```
SET vpn_bot:ai_settings  → {"prompt": "...", "temperature": 0.7, "auto_reply": true, "handoff_enabled": true}
SET vpn_bot:schedule     → {"mon": {"enabled": true, "from": "09:00", "to": "21:00"}, ...}
```

N8n должен читать эти ключи при каждом запросе к AI вместо захардкоженных значений.

---

## Мониторинг VPN-серверов

Мониторинг реализован в Python (`app/servers.py`), n8n не нужен.
Фоновая задача проверяет серверы каждые `SERVERS_CHECK_INTERVAL` секунд.

### Конфигурация (.env)

```env
SERVERS_MONITOR_TYPE=tcp          # tcp | http | stub
SERVERS_CHECK_INTERVAL=300        # секунды
SERVERS_HEALTH_PATH=/health       # только для type=http

SERVERS=[
  {"name":"Frankfurt-01","host":"1.2.3.4","port":443,"location":"DE"},
  {"name":"Amsterdam-03","host":"5.6.7.8","port":443,"location":"NL","load_warn_pct":75}
]
```

### Типы мониторинга

| Тип | Как работает | Когда использовать |
|---|---|---|
| `tcp` | TCP-подключение к `host:port`, измеряет пинг | Для любого сервера — просто и надёжно |
| `http` | GET `host:port/health`, читает `load` и `uptime` из JSON | Если на серверах есть health-эндпоинт |
| `stub` | Фиктивные данные | Разработка / тестирование |

### HTTP health-endpoint (для type=http)

Python ожидает от сервера JSON (поля опциональны):
```json
{ "load": 42.5, "uptime": 99.9 }
```

### Подключить своя логику проверки

```python
# app/servers.py
class MyMonitor(ServerMonitor):
    async def check_one(self, server: ServerInfo) -> ServerResult:
        # Вызов твоего management API, SSH, SNMP — что угодно
        data = await my_api.get_server_stats(server.host)
        return ServerResult(
            name=server.name,
            location=server.location,
            status="ok" if data["alive"] else "down",
            load=data.get("cpu_pct"),
            ping=data.get("latency_ms"),
            uptime=data.get("uptime_pct"),
        )
```

Зарегистрировать в `main.py`:
```python
server_monitor = MyMonitor(servers=[...], interval=300)
```

---

## Файлы пользователей (фото, документы)

Telegram файлы нельзя отобразить в браузере по `file_id`. Схема работы:

```
1. Пользователь отправил фото в Telegram
2. n8n получает file_id, скачивает файл через Telegram API
3. n8n POST /api/upload  (multipart/form-data)
4. Python сохраняет файл, возвращает { "url": "/api/files/abc123.jpg" }
5. n8n включает file_url в Redis-сообщение → Python → браузер отображает
```

Оператор отправляет файл в обратном направлении:
```
Оператор выбирает файл в браузере
→ POST /api/upload → получает URL
→ URL уходит в ответ вместе с сообщением
→ n8n получает file_url, скачивает, отправляет в Telegram
```

---

## Биллинг

Три действия из панели: **Продлить подписку**, **Докупить трафик**, **Сбросить ключ**.

### Подключить свой API

Задать в `.env`:
```env
BILLING_API_URL=https://billing.example.com/api
BILLING_API_TOKEN=your_secret_token
```

`HttpBillingProvider` вызовет:
```
POST /subscriptions/renew        { "chat_id": "...", "dialog_id": "..." }
POST /subscriptions/buy_traffic  { "chat_id": "...", "dialog_id": "..." }
POST /keys/reset                 { "chat_id": "...", "dialog_id": "..." }
```

### Своя схема запросов

Если формат API отличается — унаследуй и переопредели нужные методы в `app/billing.py`:

```python
class MyBilling(HttpBillingProvider):
    async def reset_key(self, chat_id: str, dialog_id: str) -> BillingResult:
        return await self._post(f"/vpn/users/{chat_id}/new-key", {})
```

Зарегистрировать в `main.py`:
```python
billing = MyBilling(settings.BILLING_API_URL, settings.BILLING_API_TOKEN)
```

Если `BILLING_API_URL` пустой — автоматически используется `StubBillingProvider` (только логи, ничего не ломается).

---

## N8n воркфлоу

### Что нужно настроить в n8n

#### 1. Входящие сообщения от пользователей

Telegram Trigger → собрать payload → `LPUSH vpn_bot:incoming`:
- Включить все поля пользователя (`user_name`, `user_plan`, трафик и т.д.)
- Если сообщение содержит файл — скачать через Telegram API и загрузить через `POST /api/upload`

#### 2. AI воркфлоу

При запуске AI-агента:
1. Прочитать `GET vpn_bot:ai_settings` — использовать `prompt` и `temperature`
2. Прочитать `GET vpn_bot:schedule` — проверить рабочие часы
3. Если вне расписания — ответить пользователю сообщением о часах работы, AI не запускать
4. Ответ AI публиковать в `LPUSH vpn_bot:incoming` с `type=ai_response`

#### 3. Отправка пользователям

Подписаться на `SUBSCRIBE vpn_bot:messages` → при получении → `bot.sendMessage(chat_id, message)`.

#### 4. Toggle AI

```
SUBSCRIBE vpn_bot:toggle_request
→ Получить текущий ai_enabled из dialogs
→ Обновить: UPDATE dialogs SET ai_enabled = NOT ai_enabled WHERE dialog_id = ...
→ LPUSH vpn_bot:toggle:{dialog_id}  { "ai_enabled": <новое значение> }
```

#### 5. Мониторинг серверов (Cron)

```
Cron каждые 5 минут
→ Пинговать каждый VPN-сервер
→ SET vpn_bot:servers  [{ name, status, load, ping, uptime, location }, ...]
→ SET vpn_bot:servers_updated  "ДД.ММ.ГГГГ ЧЧ:ММ"
```

#### 6. Уведомления оператору

```
При получении user_message с operator_called=true (или handoff-события)
→ bot.sendMessage(operator_tg_id, "Новый запрос оператора от @username")
```

### PostgreSQL-подключение из n8n

| Поле | Значение |
|---|---|
| Host | IP сервера (или `172.17.0.1` из Docker) |
| Port | `5433` |
| Database | `vpnbot` (или значение `POSTGRES_DB`) |
| User | `vpnbot` |
| Password | значение `POSTGRES_PASSWORD` из `.env` |

N8n должен работать с таблицами `dialogs` и `messages` напрямую — читать/писать в те же таблицы что и Python.

---

## Порты контейнеров

| Контейнер | Образ | Порт на хосте |
|---|---|---|
| `vpn-helpdesk` | python:3.11-slim | `8000` |
| `vpn-bot-redis` | redis:7-alpine | `6380` |
| `vpn-bot-postgres` | postgres:16-alpine | `5433` |
| `vpn-bot-qdrant` | qdrant/qdrant | `6333`, `6334` |

---

## Обновление

```bash
git pull
docker compose up -d --build   # пересобрать образ с новым кодом
```

База данных обновляется автоматически при старте — новые колонки добавятся через `ALTER TABLE`.
