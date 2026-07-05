# VPN Helpdesk — веб-панель техподдержки

Веб-интерфейс для операторов техподдержки VPN-сервиса. Заменяет старый интерфейс на основе Telegram-топиков.

---

## Архитектура

```
Пользователь (Telegram)
        │
        ▼
    n8n webhook / Telegram Trigger
        │  (AI воркфлоу, обработка сообщений)
        ▼
      Redis
        │ vpn_bot:incoming (LPUSH)         vpn_bot:outgoing (LPUSH/LPOP)
        │  ◄── n8n пишет сюда              ──► n8n читает отсюда
        ▼
  Python (FastAPI)
  ├── REST API
  ├── WebSocket (реал-тайм)
  ├── PostgreSQL (диалоги, сообщения, операторы, KB, шаблоны)
  ├── Qdrant    (векторный поиск по базе знаний)
  └── Billing API (внешние вызовы)
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
| AI-настройки и расписание | PostgreSQL + Redis для n8n |
| Статистика | SQL-запросы напрямую |
| Загрузка файлов | `/api/upload`, хранение локально или в S3 |
| Биллинг (продлить, трафик, ключ) | Прямой вызов внешнего API через `BillingProvider` |
| Статусы VPN-серверов | Фоновая задача `app/servers.py` (TCP/HTTP/stub) |
| База знаний (KB) | Загрузка документов, чанкинг + Qdrant |
| Классификация сообщений | LLM-классификатор по категориям |
| Автосуммаризация диалога | LLM, до 8 слов — тема обращения |
| Автораспределение тикетов | Наименее загруженный онлайн-оператор |
| Очередь тикетов | Тикеты сверх лимита → очередь → слив при освобождении |
| Шаблоны ответов | CRUD, группировка по категориям |
| Массовая рассылка | POST `/api/broadcast` ко всем chat_id |

### n8n (внешний, не в этом репо)

| Функция | Почему в n8n |
|---|---|
| Приём Telegram-вебхука | Telegram API-интеграция без кода |
| AI воркфлоу (LLM + RAG) | Визуальное редактирование без деплоя |
| Маршрутизация исходящих сообщений | Читает `vpn_bot:outgoing`, роутит по `type` |
| Отправка inline-кнопок | Telegram Bot API: `reply_markup` |

---

## Структура проекта

```
vpn_bot_support/
├── app/
│   ├── ai_client.py        # Фабрика LLM-клиентов (openai / gemini)
│   ├── auth.py             # Хэширование паролей, cookie-сессии
│   ├── billing.py          # Биллинг-провайдеры (OOP, легко заменить)
│   ├── classifier.py       # LLM-классификатор входящих сообщений
│   ├── config.py           # Все настройки (читает .env)
│   ├── database.py         # PostgreSQL: схема + миграции
│   ├── kb.py               # Загрузка документов в Qdrant (KB)
│   ├── n8n_client.py       # Отправка событий в Redis → n8n
│   ├── redis_consumer.py   # Чтение входящих сообщений из Redis
│   ├── servers.py          # Мониторинг VPN-серверов
│   ├── storage.py          # Хранилище файлов: LocalStorage / S3Storage
│   ├── summarizer.py       # LLM-суммаризатор диалога
│   ├── telegram_bot.py     # Опциональный встроенный Telegram-бот
│   ├── web_server.py       # FastAPI: все REST-эндпоинты + WebSocket
│   ├── ws_manager.py       # WebSocket broadcast менеджер
│   └── static/             # React SPA (без сборщика)
│       ├── index.html      # App shell + TopBar
│       ├── components.jsx  # Avatar, Icon, Toast, Badge
│       ├── dialogs.jsx     # Экран диалогов (Мои/Все, очередь, передача)
│       ├── statistics.jsx  # Экран статистики
│       ├── servers.jsx     # Экран серверов VPN
│       └── settings.jsx    # Операторы, расписание, AI-настройки, KB
├── n8n_outgoing_router.json  # Готовый n8n воркфлоу (импортировать)
├── main.py                 # Точка входа
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Быстрый старт

```bash
git clone <repo>
cd vpn_bot_support

cp .env.example .env
# Обязательно заполнить: POSTGRES_PASSWORD, SECRET_KEY
# Опционально: ADMIN_INIT_TG, ADMIN_INIT_PASSWORD — создаст первого администратора

docker compose up -d --build
# Панель: http://localhost:8000
```

> После `git pull` всегда делай `docker compose up -d --build` —
> статические файлы копируются в образ при сборке.

При старте в консоль выводятся учётные данные всех операторов:
```
==================================================
  HELPDESK LOGIN CREDENTIALS
==================================================
  [ADMIN] @ivan  (✓ password set)
==================================================
```

---

## Переменные окружения (.env)

### Обязательные

| Переменная | Описание |
|---|---|
| `POSTGRES_PASSWORD` | Пароль PostgreSQL |
| `SECRET_KEY` | Ключ подписи сессионных cookie. Сгенерировать: `python -c "import secrets; print(secrets.token_hex(32))"` |

### Аутентификация и первый администратор

| Переменная | По умолчанию | Описание |
|---|---|---|
| `ADMIN_INIT_TG` | — | Telegram @username первого администратора (без @). Используется один раз при первом запуске или если у оператора нет пароля. |
| `ADMIN_INIT_PASSWORD` | — | Пароль первого администратора |

### PostgreSQL

| Переменная | По умолчанию | Описание |
|---|---|---|
| `POSTGRES_HOST` | `postgres` | Хост |
| `POSTGRES_PORT` | `5432` | Порт |
| `POSTGRES_DB` | `vpnbot` | Имя базы данных |
| `POSTGRES_USER` | `vpnbot` | Пользователь |

### Redis

| Переменная | По умолчанию | Описание |
|---|---|---|
| `REDIS_URL` | `redis://redis:6379` | URL Redis |

### Веб-сервер

| Переменная | По умолчанию | Описание |
|---|---|---|
| `WEB_HOST` | `0.0.0.0` | Хост |
| `WEB_PORT` | `8000` | Порт |
| `BASE_URL` | — | Публичный URL (scheme+host) для абсолютных ссылок на файлы, например `https://helpdesk.example.com`. Нужен когда n8n пересылает файлы в Telegram. |
| `BASE_URL_PATH` | — | Путь-префикс если nginx проксирует без strip, например `/files` |

### Файлы и хранилище

| Переменная | По умолчанию | Описание |
|---|---|---|
| `UPLOADS_DIR` | `app/uploads` | Директория для локального хранения файлов |
| `N8N_API_KEY` | — | API-ключ для эндпоинта `/api/n8n/upload` (n8n загружает файлы из Telegram). Сгенерировать: `python -c "import secrets; print(secrets.token_hex(24))"` |
| `S3_BUCKET` | — | Имя S3-бакета. Если задано вместе с `S3_ACCESS_KEY` — используется S3 вместо локального диска |
| `S3_ENDPOINT_URL` | — | URL эндпоинта (AWS S3, R2, MinIO, Yandex OS и т.д.) |
| `S3_ACCESS_KEY` | — | Access key |
| `S3_SECRET_KEY` | — | Secret key |
| `S3_REGION` | `us-east-1` | Регион |
| `S3_PUBLIC_URL` | — | CDN или кастомный домен для публичных ссылок на файлы |

### AI (классификация, суммаризация, KB)

| Переменная | По умолчанию | Описание |
|---|---|---|
| `CHAT_PROVIDER` | `openai` | Провайдер LLM: `openai` или `gemini` |
| `OPENAI_API_KEY` | — | Ключ OpenAI. Обязателен для KB (эмбеддинги всегда через OpenAI), для `openai`-провайдера |
| `GEMINI_API_KEY` | — | Ключ Google Gemini. Нужен только при `CHAT_PROVIDER=gemini` |
| `QDRANT_URL` | `http://qdrant:6333` | URL Qdrant (для базы знаний) |

### Биллинг

| Переменная | По умолчанию | Описание |
|---|---|---|
| `BILLING_API_URL` | — | URL биллингового API. Если пустой — используется заглушка |
| `BILLING_API_TOKEN` | — | Bearer-токен биллингового API |

### Мониторинг серверов

| Переменная | По умолчанию | Описание |
|---|---|---|
| `SERVERS_MONITOR_TYPE` | `stub` | Тип мониторинга: `tcp` \| `http` \| `stub` |
| `SERVERS_CHECK_INTERVAL` | `300` | Интервал проверки (секунды) |
| `SERVERS_HEALTH_PATH` | `/health` | Путь health-эндпоинта (только для `type=http`) |
| `SERVERS` | `[]` | JSON-список серверов (см. раздел Мониторинг) |

---

## Аутентификация

Операторы логинятся по Telegram @username и паролю. Сессия хранится в `httpOnly`-cookie.

### Роли

| Роль | Возможности |
|---|---|
| `admin` | Всё: управление операторами, настройки, передача любых диалогов |
| `agent` | Работа с диалогами, передача только своих тикетов |

### Первый вход

1. Задать `ADMIN_INIT_TG` и `ADMIN_INIT_PASSWORD` в `.env`
2. Запустить — при старте создаётся оператор с ролью `admin`
3. Войти на `http://localhost:8000` с этими учётными данными
4. Через панель настроек добавить остальных операторов и задать им пароли

### Смена пароля

```
PUT /api/auth/password  { "old_password": "...", "new_password": "..." }
```

---

## Автораспределение тикетов

При поступлении нового тикета система автоматически назначает его наименее загруженному **онлайн**-оператору.

### Алгоритм

1. Найти оператора с `online=true` и наименьшим числом активных (не `closed`) тикетов
2. Если у всех операторов тикетов ≥ `max_tickets_per_operator` — тикет остаётся в очереди (`assigned_operator IS NULL`)
3. Очередь сливается автоматически когда оператор:
   - закрывает тикет
   - выходит онлайн через WebSocket

### Настройка

В панели **Настройки → Автоматизация**:

| Параметр | По умолчанию | Описание |
|---|---|---|
| `max_tickets_per_operator` | `10` | Максимум активных тикетов на оператора |
| `operator_button_enabled` | `false` | Показывать кнопку «Позвать оператора» |
| `operator_button_after_msgs` | `3` | После скольких сообщений показывать кнопку |

### Передача тикета

```
POST /api/dialogs/{dialog_id}/transfer  { "operator_name": "Петров" }
```

- Оператор может передать только **свой** тикет
- Администратор — **любой** тикет
- При передаче старый оператор освобождает слот → срабатывает слив очереди

### Вкладки в панели

- **Мои** — тикеты назначенные текущему оператору
- **Все** — все тикеты (доступна администраторам и при ручном взятии)
- Тикеты без оператора отображаются с меткой «В очереди»

---

## База знаний (KB)

Документы загружаются, автоматически разбиваются на чанки и индексируются в Qdrant.

### Загрузка

```
POST /api/kb/upload  (multipart/form-data: file=<pdf|txt|md|docx>)
```

Процесс:
1. LLM разбивает документ на семантически независимые чанки
2. Чанки эмбеддятся через `text-embedding-3-small` (OpenAI)
3. Векторы сохраняются в Qdrant (коллекция `kb`)
4. Метаданные (`title`, `category`, `keywords`, `content`) — в PostgreSQL

### Управление статьями

```
GET    /api/kb                    — список всех статей
DELETE /api/kb/{article_id}       — удалить статью
```

### Требования

- `OPENAI_API_KEY` — обязателен для эмбеддингов
- `QDRANT_URL` — должен быть доступен (включён в `docker-compose.yml`)

---

## Шаблоны ответов

Быстрые ответы с группировкой по категориям. Доступны оператору в чате.

```
GET    /api/templates
POST   /api/templates             { "group_name": "Тарифы", "title": "Продление", "text": "..." }
PUT    /api/templates/{id}
DELETE /api/templates/{id}
```

---

## Массовая рассылка

Отправить текстовое сообщение всем пользователям (всем `chat_id` из таблицы `dialogs`):

```
POST /api/broadcast  { "text": "Плановые работы с 23:00 до 01:00" }
```

Сообщение ставится в очередь через `vpn_bot:outgoing` и доставляется n8n-воркфлоу.

---

## База данных

`init_db()` запускается при каждом старте и безопасен для повторного запуска:

- **Свежая установка** — создаёт все таблицы
- **Обновление** — добавляет новые колонки через `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
- **Миграция со старой системы** (Telegram-топики) — старые таблицы `dialogs`, `messages`, `chat_topics` автоматически переименуются в `*_legacy`, новые создадутся рядом

### Таблицы

**`dialogs`** — одно обращение пользователя:

```
dialog_id             TEXT PK   — уникальный ID из n8n
chat_id               TEXT      — Telegram user ID
status                TEXT      — new | in_progress | closed
assigned_operator     TEXT      — имя назначенного оператора (NULL = в очереди)
ai_enabled            BOOL      — включён ли AI
operator_called       BOOL      — пользователь нажал «позвать оператора»
rating                SMALLINT  — оценка 1–5 (звёзды), NULL если не оценён
unread_count          INT       — счётчик непрочитанных
user_name/username    TEXT      — имя и @username
user_plan             TEXT      — тариф: Basic / Pro / ...
user_sub_status       TEXT      — active | expired | ...
user_next_payment     TEXT      — дата следующего платежа
user_traffic_used/total FLOAT  — использованный и общий трафик (ГБ)
last_payment_amount/date TEXT  — последний платёж
last_message_text     TEXT      — превью последнего сообщения
```

**`messages`** — сообщения в диалоге:

```
dialog_id     TEXT     — ссылка на dialogs
kind          TEXT     — user | ai | operator | system
text          TEXT     — текст сообщения
file_id       TEXT     — Telegram file_id
file_type     TEXT     — photo | document | voice
file_url      TEXT     — URL файла на сервере (/api/files/...)
operator_name TEXT     — имя оператора если kind=operator
category      TEXT     — категория (заполняется классификатором)
```

**`operators`** — учётные записи операторов:

```
name          TEXT   — отображаемое имя
tg            TEXT   — @username (используется для логина)
tg_id         BIGINT — Telegram user ID (нужен для уведомлений)
role          TEXT   — admin | agent
password_hash TEXT
online        BOOL
initials      TEXT   — аватар (первые буквы имени)
color         TEXT   — цвет аватара
notif_prefs   TEXT   — JSON настройки уведомлений
```

**`settings`** — ключ-значение для настроек:

```
key=ai_settings   → JSON: prompt, temperature, auto_reply, handoff_enabled, classification_enabled
key=schedule      → JSON: {"mon": {"enabled": true, "from": "09:00", "to": "21:00"}, ...}
key=automation    → JSON: max_tickets_per_operator, operator_button_enabled, operator_button_after_msgs
```

**`kb_articles`** — метаданные чанков базы знаний:

```
id, title, category, keywords, content (полный текст чанка)
```

**`message_templates`** — шаблоны быстрых ответов:

```
group_name, title, text
```

---

## Redis: протокол обмена с n8n

### n8n → Python: входящие (`LPUSH vpn_bot:incoming`)

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
  "operator_called": false,
  "user_name": "Иван Иванов",
  "user_username": "@ivan",
  "user_plan": "Pro",
  "user_sub_status": "active",
  "user_next_payment": "2025-06-01",
  "user_traffic_used": 45.2,
  "user_traffic_total": 100,
  "user_last_payment_amount": "299",
  "user_last_payment_date": "2025-05-01"
}
```

**Ответ AI:**
```json
{
  "type": "ai_response",
  "dialog_id": "42",
  "message": "Попробуйте переподключиться. [HANDOFF] — добавить токен чтобы передать оператору"
}
```

> Если в тексте AI-ответа есть `[HANDOFF]` — Python автоматически переводит диалог к оператору (auto-handoff).

**Callback от пользователя (inline-кнопка):**
```json
{
  "type": "callback",
  "callback_data": "call_op:42"
}
```

| `callback_data` | Что делает Python |
|---|---|
| `call_op:{dialog_id}` | Помечает `operator_called=true`, уведомляет оператора |
| `rate:{dialog_id}:{1-5}` | Сохраняет оценку в `dialogs.rating` |

### Python → n8n: исходящие (`RPUSH vpn_bot:outgoing`, n8n читает через `LPOP`)

> **Важно:** используется Redis **список** (не pub/sub).
> Импортировать `n8n_outgoing_router.json` для готового воркфлоу-маршрутизатора.

**Ответ оператора пользователю:**
```json
{
  "type": "manager_message",
  "dialog_id": "42",
  "chat_id": "123456789",
  "message": "Сейчас проверим",
  "file_id": "https://example.com/api/files/doc.pdf",
  "file_type": "document"
}
```

**Проактивное сообщение пользователю (без файла, опционально с inline-кнопками):**
```json
{
  "type": "send_to_user",
  "chat_id": "123456789",
  "text": "Нужна помощь живого оператора? 👇",
  "keyboard": [[{"text": "👨‍💼 Позвать оператора", "callback_data": "call_op:42"}]]
}
```

**Уведомление операторам:**
```json
{
  "type": "operator_notify",
  "event": "new_dialog",
  "dialog_id": "42",
  "username": "@ivan"
}
```

| `event` | Поля | Смысл |
|---|---|---|
| `new_dialog` | `dialog_id`, `username` | Пришёл новый тикет |
| `operator_called` | `dialog_id`, `username` | Пользователь вызвал оператора |
| `dialog_closed` | `dialog_id`, `operator_name` | Диалог закрыт |
| `ai_toggled` | `dialog_id`, `ai_enabled` | Включён/выключен AI |
| `server_down` | `server_name`, `location` | VPN-сервер недоступен |

**Команда биллинга:**
```json
{
  "type": "billing_action",
  "dialog_id": "42",
  "chat_id": "123456789",
  "action": "renew_subscription"
}
```

### Расписание уведомлений

`schedule_notify` — уведомления с учётом рабочих часов:
- В рабочее время → немедленная отправка
- Вне рабочих часов → ставится в `vpn_bot:pending_notifications`
- При следующей отправке в рабочее время — очередь сбрасывается

Настройка расписания: панель **Настройки → Расписание**.

---

## n8n: настройка воркфлоу

### Исходящий роутер через Webhook (рекомендуется)

RabbitMQ Trigger в n8n нестабилен (соединение отваливается и нода не переподключается),
поэтому исходящие события можно доставлять в n8n обычным HTTP-вебхуком.
В репозитории лежит `n8n_outgoing_webhook_router.json` — тот же роутер, но с Webhook-триггером.

1. Импортировать: n8n → Workflows → Import from file → `n8n_outgoing_webhook_router.json`
2. В n8n Settings → Variables добавить:
   - `N8N_API_KEY` — то же значение, что в `.env` бэкенда (проверка заголовка `X-API-Key`)
   - `TELEGRAM_BOT_TOKEN` — токен бота для отправки сообщений с кнопками
   - `BILLING_API_URL` — если используется биллинг
3. Проверить, что креды Postgres / Telegram подтянулись по ID, активировать воркфлоу
4. В `.env` бэкенда задать:
   ```
   N8N_WEBHOOK_URL=https://<n8n-host>/webhook/vpn-bot-outgoing
   ```
   и перезапустить бэкенд
5. Старый воркфлоу с RabbitMQ Trigger выключить (можно оставить как резерв —
   при недоступности вебхука бэкенд после 3 ретраев публикует сообщение
   в очередь `vpn_bot.outgoing` как раньше)

Если `N8N_WEBHOOK_URL` не задан — поведение прежнее, всё идёт через RabbitMQ.

### Импорт готового роутера

В репозитории лежит `n8n_outgoing_router.json` — готовый воркфлоу-маршрутизатор исходящих сообщений.

**Импортировать:** n8n → Workflows → Import from file → выбрать `n8n_outgoing_router.json`

После импорта:
1. Добавить переменную `TELEGRAM_BOT_TOKEN` в n8n Settings → Variables
2. Проверить что кредиты Redis / Postgres / Telegram подтянулись по ID
3. При необходимости добавить `BILLING_API_URL` в Variables
4. Активировать воркфлоу

### Входящий воркфлоу (настроить вручную)

**Telegram Trigger → обогащение данными → `LPUSH vpn_bot:incoming`**

Обязательные поля в payload:
- `type: "user_message"`
- `dialog_id`, `chat_id`, `message`
- Поля пользователя: `user_name`, `user_username`, `user_plan`, `user_sub_status`, `user_next_payment`, `user_traffic_used`, `user_traffic_total`
- Если сообщение с файлом: скачать через Telegram API → `POST /api/n8n/upload` (с заголовком `X-API-Key`) → записать `file_url` и `file_type`

**AI-воркфлоу:**
1. Прочитать `ai_settings` из Redis (ключ `vpn_bot:ai_settings`) — использовать `prompt`, `temperature`
2. Прочитать `schedule` из Redis (ключ `vpn_bot:schedule`) — если вне расписания не запускать AI
3. Ответ AI опубликовать в `LPUSH vpn_bot:incoming` с `type: "ai_response"`

**Обработка callback_query:**  
Telegram inline-кнопки посылают `callback_query` — добавить отдельную ветку в Telegram Trigger:
```json
{
  "type": "callback",
  "callback_data": "{{ callback_query.data }}"
}
```

### Подключение Postgres из n8n

| Поле | Значение |
|---|---|
| Host | IP сервера (или `172.17.0.1` из Docker) |
| Port | `5433` |
| Database | `vpnbot` |
| User | `vpnbot` |
| Password | значение `POSTGRES_PASSWORD` из `.env` |

---

## WebSocket API (`/ws`)

Клиент подключается с cookie-сессией. Все события широковещательные (broadcast всем онлайн-операторам).

| `type` | Поля | Когда |
|---|---|---|
| `new_dialog` | `dialog` | Пришёл первый тикет от пользователя |
| `new_message` | `dialog_id`, `message` | Новое сообщение в существующем диалоге |
| `dialog_updated` | `dialog` | Изменился статус, оператор, флаги диалога |
| `operator_status` | `op_id`, `online: bool` | Оператор вышел онлайн / ушёл офлайн |

Оператор отправляет в сокет при подключении:
```json
{ "type": "ping" }
```
Это регистрирует его как онлайн и запускает слив очереди тикетов.

---

## REST API: основные эндпоинты

### Аутентификация

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/auth/status` | Первый запуск: нужен ли setup |
| POST | `/api/auth/setup` | Создать первого оператора (до первого входа) |
| POST | `/api/auth/login` | Войти |
| POST | `/api/auth/logout` | Выйти |
| GET | `/api/auth/me` | Текущий оператор |
| PUT | `/api/auth/password` | Сменить пароль |

### Диалоги

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/dialogs` | Все диалоги |
| GET | `/api/dialogs/{id}` | Один диалог |
| GET | `/api/dialogs/{id}/messages` | Сообщения |
| GET | `/api/dialogs/{id}/history` | История диалогов пользователя (тот же chat_id) |
| POST | `/api/dialogs/{id}/reply` | Ответить (текст и/или файл) |
| POST | `/api/dialogs/{id}/comment` | Внутренний комментарий оператора (не виден пользователю) |
| POST | `/api/dialogs/{id}/toggle_ai` | Включить/выключить AI |
| POST | `/api/dialogs/{id}/handoff` | Взять в работу / передать на 2-ю линию |
| POST | `/api/dialogs/{id}/transfer` | Передать другому оператору |
| POST | `/api/dialogs/{id}/reopen` | Переоткрыть закрытый диалог |
| POST | `/api/dialogs/{id}/close` | Закрыть диалог (опционально — запросить оценку) |
| POST | `/api/dialogs/{id}/billing/{action}` | Биллинг: `renew` \| `traffic` \| `reset_key` |

### Операторы

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/operators` | Список операторов |
| POST | `/api/operators` | Создать оператора |
| PUT | `/api/operators/{id}` | Обновить |
| DELETE | `/api/operators/{id}` | Удалить |
| GET | `/api/operators/me/notifications` | Настройки уведомлений |
| PUT | `/api/operators/me/notifications` | Сохранить настройки уведомлений |

### Настройки

| Метод | Путь | Описание |
|---|---|---|
| GET/PUT | `/api/settings/ai` | AI-настройки |
| GET/PUT | `/api/settings/schedule` | Расписание |
| GET/PUT | `/api/settings/automation` | Автоматизация |

### База знаний, шаблоны, рассылка

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/kb` | Список статей KB |
| POST | `/api/kb/upload` | Загрузить документ (PDF/TXT/MD/DOCX) |
| DELETE | `/api/kb/{id}` | Удалить статью |
| GET | `/api/templates` | Список шаблонов |
| POST | `/api/templates` | Создать |
| PUT | `/api/templates/{id}` | Обновить |
| DELETE | `/api/templates/{id}` | Удалить |
| POST | `/api/broadcast` | Рассылка всем пользователям |

### Прочее

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/servers` | Статус VPN-серверов |
| GET | `/api/stats?days=14` | Статистика диалогов |
| GET | `/api/stats/times?days=30` | Статистика по времени суток |
| POST | `/api/upload` | Загрузить файл (от оператора) |
| POST | `/api/n8n/upload` | Загрузить файл (от n8n, требует `X-API-Key`) |
| GET | `/api/files/{filename}` | Скачать файл |

---

## Мониторинг VPN-серверов

Фоновая задача проверяет серверы каждые `SERVERS_CHECK_INTERVAL` секунд. При падении — уведомление операторам через `vpn_bot:outgoing`.

### Конфигурация

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

| Тип | Как работает |
|---|---|
| `tcp` | TCP-подключение к `host:port`, измеряет пинг |
| `http` | GET `host:port/health`, читает `load` и `uptime` из JSON |
| `stub` | Фиктивные данные для разработки |

### Своя логика проверки

```python
# app/servers.py
class MyMonitor(ServerMonitor):
    async def check_one(self, server: ServerInfo) -> ServerResult:
        data = await my_api.get_server_stats(server.host)
        return ServerResult(
            name=server.name, location=server.location,
            status="ok" if data["alive"] else "down",
            load=data.get("cpu_pct"),
            ping=data.get("latency_ms"),
            uptime=data.get("uptime_pct"),
        )
```

Зарегистрировать в `main.py` вместо `make_server_monitor(...)`.

---

## Файлы пользователей

Telegram-файлы нельзя отобразить в браузере по `file_id`. Схема:

```
1. Пользователь → Telegram файл
2. n8n скачивает через Telegram API
3. n8n POST /api/n8n/upload  (multipart + X-API-Key: N8N_API_KEY)
4. Python сохраняет → { "url": "/api/files/abc123.jpg" }
5. n8n включает file_url в Redis-сообщение
6. Браузер отображает: <img src="/api/files/abc123.jpg">
```

Оператор → пользователь:
```
Оператор прикрепляет файл в браузере
→ POST /api/upload → URL
→ URL + сообщение → vpn_bot:outgoing
→ n8n скачивает URL, отправляет в Telegram
```

### S3-хранилище

Если заданы `S3_BUCKET` и `S3_ACCESS_KEY` — файлы сохраняются в S3 вместо локального диска. Совместимо с AWS S3, Cloudflare R2, MinIO, Yandex Object Storage.

---

## Биллинг

Три действия: **Продлить подписку**, **Докупить трафик**, **Сбросить ключ**.

### Подключить API

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

```python
# app/billing.py
class MyBilling(HttpBillingProvider):
    async def reset_key(self, chat_id: str, dialog_id: str) -> BillingResult:
        return await self._post(f"/vpn/users/{chat_id}/new-key", {})
```

Если `BILLING_API_URL` пустой — автоматически `StubBillingProvider` (только логи).

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
