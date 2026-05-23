# VPN Bot Support — Helpdesk для VPN-сервиса

Веб-панель операторов поддержки, интегрированная с Telegram через n8n. Операторы видят диалоги с клиентами в реальном времени, отвечают на сообщения, управляют биллингом и следят за состоянием серверов. AI-ассистент отвечает автоматически пока не нужен живой оператор.

---

## Содержание

1. [Архитектура](#1-архитектура)
2. [Компоненты системы](#2-компоненты-системы)
3. [Redis: протокол обмена с n8n](#3-redis-протокол-обмена-с-n8n)
4. [HTTP-эндпоинты для n8n](#4-http-эндпоинты-для-n8n)
5. [Переменные окружения](#5-переменные-окружения)
6. [Деплой](#6-деплой)
7. [Первый запуск и инициализация](#7-первый-запуск-и-инициализация)
8. [Настройка n8n](#8-настройка-n8n)
9. [Жизненный цикл диалога](#9-жизненный-цикл-диалога)
10. [Биллинг](#10-биллинг)
11. [Мониторинг серверов](#11-мониторинг-серверов)
12. [База знаний (KB)](#12-база-знаний-kb)
13. [Файлы: фото, документы](#13-файлы-фото-документы)
14. [Структура базы данных](#14-структура-базы-данных)
15. [REST API](#15-rest-api)
16. [WebSocket](#16-websocket)
17. [Устранение неполадок](#17-устранение-неполадок)

---

## 1. Архитектура

```
Пользователь (Telegram)
       │
       ▼
   n8n Webhook ◄──────────────────────────────────────┐
       │                                               │
       │  1. Принимает сообщение из Telegram            │
       │  2. Читает настройки AI и расписание из Redis  │
       │  3. Вызывает LLM (если AI включён)             │
       │  4. Загружает файлы через /api/n8n/upload      │
       │  5. Кладёт сообщение в Redis-очередь           │
       ▼                                               │
  Redis List                                          │
  vpn_bot:incoming                                    │
       │                                               │
       ▼                                               │
  Python / FastAPI + PostgreSQL                        │
  redis_consumer.py (фоновый воркер)                  │
       │                                               │
       │  • Сохраняет диалоги и сообщения в PostgreSQL  │
       │  • Классифицирует сообщения через LLM          │
       │  • Рассылает обновления по WebSocket           │
       │  • Принимает ответы операторов через REST API  │
       │  • Публикует ответы оператора в Redis ─────────┘
       │    канал vpn_bot:messages
       ▼
  Браузер оператора (React SPA)
  └── WebSocket /ws — обновления в реальном времени
```

**Ключевой принцип:** n8n и Python не вызывают друг друга напрямую по HTTP (за исключением загрузки файлов). Они общаются через Redis: очередь для сообщений от n8n к Python, pub/sub-каналы для событий от Python к n8n. Это делает систему устойчивой к временным сбоям: если хелпдеск перезапускается, сообщения в очереди не теряются.

---

## 2. Компоненты системы

### Backend (Python / FastAPI)

| Файл | Назначение |
|------|-----------|
| `main.py` | Точка входа, инициализация всех сервисов и фоновых задач |
| `app/config.py` | Настройки через Pydantic Settings — читает `.env` |
| `app/web_server.py` | Все REST и WebSocket эндпоинты |
| `app/database.py` | Схема PostgreSQL, идемпотентные миграции, CRUD |
| `app/redis_consumer.py` | Воркер: читает `vpn_bot:incoming`, обрабатывает сообщения |
| `app/n8n_client.py` | Публикует события в Redis для n8n |
| `app/ws_manager.py` | Широковещательная рассылка по всем WebSocket-соединениям |
| `app/auth.py` | JWT-токены (HS256, 30 дней), bcrypt для паролей |
| `app/billing.py` | Биллинг-провайдеры: `StubBillingProvider`, `HttpBillingProvider` |
| `app/servers.py` | Мониторинг VPN-серверов: TCP, HTTP или stub |
| `app/ai_client.py` | Фабрика LLM-клиентов: OpenAI или Gemini |
| `app/classifier.py` | Классификация сообщений по категориям через LLM |
| `app/summarizer.py` | Краткое резюме диалога при закрытии (через LLM) |
| `app/kb.py` | База знаний: чанкинг, эмбеддинги, Qdrant |
| `app/storage.py` | Хранилище файлов: локальный диск или S3 |

### Frontend (React SPA)

Без сборщика — JSX компилируется в браузере через Babel CDN. Для изменения UI достаточно отредактировать файл и перезагрузить страницу (без `npm run build`).

| Файл | Назначение |
|------|-----------|
| `app/static/index.html` | Основная разметка, TopBar с именем оператора и статусом |
| `app/static/dialogs.jsx` | Список диалогов и интерфейс чата с операторским ответом |
| `app/static/statistics.jsx` | Дашборд: дневные и почасовые графики, топ-вопросы |
| `app/static/servers.jsx` | Таблица состояния VPN-серверов |
| `app/static/settings.jsx` | AI-настройки, расписание, управление операторами, KB |
| `app/static/components.jsx` | Переиспользуемые компоненты: Avatar, Toast, Badge и др. |

### Инфраструктура (Docker Compose)

| Сервис | Образ | Порт (внешний) | Назначение |
|--------|-------|----------------|-----------|
| `helpdesk` | python:3.11-slim | 8000 | FastAPI-приложение |
| `postgres` | postgres:16-alpine | 5433 | Основная база данных |
| `redis` | redis:7-alpine | 6380 | Очереди и pub/sub |
| `qdrant` | qdrant/qdrant:latest | 6333, 6334 | Векторная БД для KB |
| `pgadmin` | dpage/pgadmin4:7.2 | 5050 | Веб-интерфейс PostgreSQL |

Все сервисы находятся в Docker-сети `vpn_n8n_shared`. n8n подключается к этой сети извне.

---

## 3. Redis: протокол обмена с n8n

### n8n → Хелпдеск (Redis List)

**Канал:** `vpn_bot:incoming`
**Метод:** n8n делает `LPUSH`, хелпдеск забирает через `BLPOP` в фоновом воркере.

#### Тип: сообщение пользователя

```json
{
  "type": "user_message",
  "dialog_id": "12345",
  "chat_id": "987654321",
  "message": "Не работает на iOS, как починить?",
  "file_url": "/api/files/screenshot_abc.jpg",
  "file_type": "photo",
  "file_id": null,
  "ai_enabled": true,
  "operator_called": false,
  "user_name": "Иван Петров",
  "user_username": "@ivanp",
  "user_plan": "Pro",
  "user_sub_status": "active",
  "user_next_payment": "2026-06-01",
  "user_traffic_used": 45.2,
  "user_traffic_total": 100.0,
  "user_last_payment_amount": "590 руб.",
  "user_last_payment_date": "2026-05-01"
}
```

| Поле | Тип | Описание |
|------|-----|---------|
| `type` | string | Всегда `"user_message"` |
| `dialog_id` | string | Уникальный ID диалога, генерируется n8n. Повторное использование ID = новое сообщение в том же диалоге |
| `chat_id` | string | Telegram user ID (число в виде строки) |
| `message` | string | Текст сообщения. Может быть пустым если отправлен только файл |
| `file_url` | string\|null | URL файла — либо относительный `/api/files/xxx`, либо абсолютный |
| `file_type` | string\|null | `"photo"`, `"document"`, `"voice"` |
| `file_id` | string\|null | Telegram file_id (legacy-поле, сейчас не используется) |
| `ai_enabled` | bool | Может ли AI отвечать в этом диалоге |
| `operator_called` | bool | Пользователь нажал кнопку «Вызвать оператора» в Telegram |
| `user_name` | string | Имя из профиля Telegram |
| `user_username` | string | @username в Telegram |
| `user_plan` | string | Тариф: Basic, Pro, Ultimate и т.д. |
| `user_sub_status` | string | Статус подписки: `"active"`, `"expired"`, `"trial"` |
| `user_next_payment` | string | Дата следующего списания в формате YYYY-MM-DD |
| `user_traffic_used` | float | Потрачено ГБ в текущем периоде |
| `user_traffic_total` | float | Лимит ГБ по тарифу (0 = безлимит) |
| `user_last_payment_amount` | string | Сумма последнего платежа в виде строки |
| `user_last_payment_date` | string | Дата последнего платежа |

#### Тип: ответ AI

После того как n8n вызвал LLM и получил ответ, он тоже кладёт его в ту же очередь:

```json
{
  "type": "ai_response",
  "dialog_id": "12345",
  "message": "Попробуйте переустановить профиль конфигурации. Вот инструкция: ..."
}
```

> **Специальный токен `[HANDOFF]`:** если текст AI-ответа начинается с `[HANDOFF]`, хелпдеск автоматически переводит диалог на оператора — добавляет системное сообщение, устанавливает `operator_called=true` и статус `in_progress`. Это работает только если в настройках AI включён `handoff_enabled`. Пример: n8n отправляет `"[HANDOFF] Переключаю вас на специалиста"` — токен убирается из текста, остаток отправляется пользователю, диалог уходит оператору.

---

### Хелпдеск → n8n (Redis Pub/Sub)

Хелпдеск публикует события через `PUBLISH`. n8n должен подписаться на соответствующие каналы через узел Redis Subscribe.

#### Канал: `vpn_bot:messages` — ответ оператора

```json
{
  "type": "manager_message",
  "dialog_id": "12345",
  "chat_id": "987654321",
  "message": "Попробуйте зайти через WireGuard вместо OpenVPN.",
  "file_url": "https://helpdesk.example.com/api/files/instruction.pdf",
  "file_type": "document",
  "from": "manager"
}
```

n8n получает это событие и пересылает сообщение пользователю через Telegram Bot API. Если есть `file_url` — скачивает файл и отправляет как документ/фото.

#### Канал: `vpn_bot:dialog_closed` — диалог закрыт

```json
{
  "type": "dialog_closed",
  "dialog_id": "12345",
  "chat_id": "987654321",
  "operator_name": "Алексей"
}
```

n8n может отправить пользователю «Ваш вопрос решён» и/или попросить оценить поддержку.

#### Канал: `vpn_bot:ai_toggled` — AI включён/выключен

```json
{
  "type": "ai_toggled",
  "dialog_id": "12345",
  "chat_id": "987654321",
  "ai_enabled": false
}
```

n8n обновляет свою логику: если `ai_enabled: false` — больше не вызывать LLM для этого диалога.

#### Канал: `vpn_bot:notifications` — системные уведомления

```json
{
  "type": "server_down",
  "server_name": "Frankfurt-01",
  "location": "DE"
}
```

n8n может отправить алерт в Telegram-канал администраторов.

#### Канал: `vpn_bot:billing` — биллинг-действие

```json
{
  "type": "billing_action",
  "dialog_id": "12345",
  "chat_id": "987654321",
  "action": "renew"
}
```

Возможные значения `action`: `"renew"`, `"buy_traffic"`, `"reset_key"`. Если биллинг-API не настроен (используется stub) — n8n можно подписать на этот канал и обрабатывать действия самостоятельно.

---

### Настройки в Redis (ключи для n8n)

При каждом сохранении в веб-панели хелпдеск обновляет Redis-ключи. n8n читает их перед каждым вызовом LLM.

**Ключ `vpn_bot:ai_settings`:**

```json
{
  "prompt": "Ты — дружелюбный ассистент поддержки VPN-сервиса. Отвечай коротко и понятно...",
  "temperature": 0.7,
  "auto_reply": true,
  "handoff_enabled": true,
  "classification_enabled": false
}
```

| Поле | Описание |
|------|---------|
| `prompt` | Системный промпт для LLM |
| `temperature` | Температура генерации (0.0 — детерминированно, 2.0 — максимально случайно) |
| `auto_reply` | Если `false` — n8n не должен вызывать LLM, все диалоги сразу идут операторам |
| `handoff_enabled` | Если `true` — токен `[HANDOFF]` в ответе AI переводит диалог на оператора |
| `classification_enabled` | Если `true` — хелпдеск автоматически классифицирует сообщения по категориям |

**Ключ `vpn_bot:schedule`:**

```json
{
  "mon": {"enabled": true, "from": "09:00", "to": "21:00"},
  "tue": {"enabled": true, "from": "09:00", "to": "21:00"},
  "wed": {"enabled": true, "from": "09:00", "to": "21:00"},
  "thu": {"enabled": true, "from": "09:00", "to": "21:00"},
  "fri": {"enabled": true, "from": "09:00", "to": "21:00"},
  "sat": {"enabled": false, "from": "10:00", "to": "18:00"},
  "sun": {"enabled": false, "from": "10:00", "to": "18:00"}
}
```

n8n проверяет этот ключ перед вызовом AI. В нерабочее время — не вызывать LLM, а отправить пользователю уведомление «Мы ответим в рабочее время» или ничего не делать.

---

## 4. HTTP-эндпоинты для n8n

### Загрузка файла от пользователя

n8n скачивает файл из Telegram и загружает его в хелпдеск:

```
POST /api/n8n/upload
Header: X-API-Key: {N8N_API_KEY}
Content-Type: multipart/form-data
Body: file=<бинарное содержимое файла>
```

**Ответ:**
```json
{"url": "/api/files/d8f3a1bc2e.jpg"}
```

Этот URL нужно включить в поле `file_url` при отправке сообщения в Redis-очередь `vpn_bot:incoming`. Если `BASE_URL` настроен — ссылка будет абсолютной и n8n сможет отдать её прямо в Telegram.

### Скачивание файла

```
GET /api/files/{filename}
```

Публичный эндпоинт без авторизации. n8n использует его чтобы получить файл, отправленный оператором, перед пересылкой пользователю в Telegram.

> **Важно:** чтобы n8n мог использовать файловые ссылки, переменная `BASE_URL` должна быть задана (например, `https://helpdesk.example.com`). Иначе n8n получит относительный путь `/api/files/xxx` и не сможет его скачать.

---

## 5. Переменные окружения

Создайте `.env` из `.env.example` и заполните значения.

### Обязательные

| Переменная | Пример | Описание |
|-----------|--------|---------|
| `SECRET_KEY` | `a3f8b2c1...` (64 hex-символа) | Ключ подписи JWT. Генерация: `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `POSTGRES_PASSWORD` | `mypassword123` | Пароль PostgreSQL |

### Сервер приложения

| Переменная | По умолчанию | Описание |
|-----------|-------------|---------|
| `WEB_HOST` | `0.0.0.0` | Адрес прослушивания FastAPI |
| `WEB_PORT` | `8000` | Порт FastAPI |
| `BASE_URL` | — | Публичный URL хелпдеска, например `https://helpdesk.example.com`. Нужен для формирования абсолютных ссылок на файлы, которые n8n пересылает в Telegram. Без него ссылки будут относительными и нерабочими. |
| `BASE_URL_PATH` | — | Префикс пути если хелпдеск находится за nginx по субпути, например `/helpdesk`. Вычитается из маршрутов. |

### База данных

| Переменная | По умолчанию | Описание |
|-----------|-------------|---------|
| `POSTGRES_HOST` | `postgres` | Хост PostgreSQL. В Docker: имя сервиса `postgres` |
| `POSTGRES_PORT` | `5432` | Порт PostgreSQL (внутренний в Docker) |
| `POSTGRES_DB` | `vpnbot` | Имя базы данных |
| `POSTGRES_USER` | `vpnbot` | Пользователь БД |

### Redis

| Переменная | По умолчанию | Описание |
|-----------|-------------|---------|
| `REDIS_URL` | `redis://redis:6379` | URL подключения к Redis. В Docker: `redis://redis:6379`, снаружи: `redis://IP:6380` |

### Первый администратор

Создаётся один раз при первом запуске, если операторов в БД ещё нет. После создания переменные можно убрать из `.env`.

| Переменная | Пример | Описание |
|-----------|--------|---------|
| `ADMIN_INIT_TG` | `@myusername` | Telegram username первого администратора (с `@`) |
| `ADMIN_INIT_PASSWORD` | `SecretPass!1` | Пароль первого администратора |

### AI / LLM

| Переменная | По умолчанию | Описание |
|-----------|-------------|---------|
| `CHAT_PROVIDER` | `openai` | Провайдер LLM: `openai` или `gemini` |
| `OPENAI_API_KEY` | — | API-ключ OpenAI. **Обязателен для эмбеддингов KB** даже если используется Gemini для чата |
| `GEMINI_API_KEY` | — | API-ключ Google Gemini. Нужен если `CHAT_PROVIDER=gemini` |

### Векторная БД

| Переменная | По умолчанию | Описание |
|-----------|-------------|---------|
| `QDRANT_URL` | `http://qdrant:6333` | URL Qdrant для хранения эмбеддингов KB |

### Интеграция с n8n

| Переменная | Пример | Описание |
|-----------|--------|---------|
| `N8N_API_KEY` | `n8n-secret-key-xyz` | Статический ключ для авторизации запросов n8n к `/api/n8n/upload`. n8n передаёт его в заголовке `X-API-Key`. Придумайте случайную строку длиной 32+ символа. |

### Биллинг

| Переменная | Пример | Описание |
|-----------|--------|---------|
| `BILLING_API_URL` | `https://billing.example.com/api` | Базовый URL внешнего биллинг-API. Если не задан — используется stub (только логи) |
| `BILLING_API_TOKEN` | `token_abc123` | Bearer-токен для авторизации в биллинг-API |

### Мониторинг серверов

| Переменная | По умолчанию | Описание |
|-----------|-------------|---------|
| `SERVERS_MONITOR_TYPE` | `stub` | Тип мониторинга: `tcp`, `http` или `stub` |
| `SERVERS_CHECK_INTERVAL` | `300` | Интервал проверки в секундах |
| `SERVERS_HEALTH_PATH` | `/health` | Путь health-эндпоинта (только для `type=http`) |
| `SERVERS` | `[]` | JSON-массив серверов (см. раздел Мониторинг) |

### Хранилище файлов

По умолчанию файлы хранятся локально:

| Переменная | По умолчанию | Описание |
|-----------|-------------|---------|
| `UPLOADS_DIR` | `app/uploads` | Путь к папке для локальных файлов |

Для S3-совместимого хранилища (MinIO, Cloudflare R2, Яндекс Object Storage):

| Переменная | Описание |
|-----------|---------|
| `S3_BUCKET` | Название бакета. **Если задано — S3 включается автоматически** вместо локального диска |
| `S3_ENDPOINT_URL` | URL S3-endpoint, например `https://s3.yandexcloud.net` |
| `S3_ACCESS_KEY` | Access Key ID |
| `S3_SECRET_KEY` | Secret Access Key |
| `S3_REGION` | Регион (по умолчанию `us-east-1`) |
| `S3_PUBLIC_URL` | CDN-URL для публичного доступа, если отличается от endpoint |

---

## 6. Деплой

### Требования

- Docker Engine 24+
- Docker Compose v2
- n8n, запущенный отдельно (и подключённый к той же Docker-сети)

### Шаг 1. Получить код

```bash
git clone https://github.com/adiga-code/vpn_bot_support.git
cd vpn_bot_support
```

### Шаг 2. Настроить окружение

```bash
cp .env.example .env
```

Минимальный рабочий `.env`:

```env
# Обязательные
SECRET_KEY=вставьте_64_hex_символа
POSTGRES_PASSWORD=надёжный_пароль

# Первый администратор
ADMIN_INIT_TG=@ваш_telegram
ADMIN_INIT_PASSWORD=ВашПароль123

# Публичный адрес хелпдеска (для файловых ссылок)
BASE_URL=https://helpdesk.example.com

# n8n API-ключ для загрузки файлов
N8N_API_KEY=случайная_строка_32_символа

# LLM (нужен хотя бы один)
OPENAI_API_KEY=sk-...
```

Сгенерировать `SECRET_KEY`:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Шаг 3. Docker-сеть для n8n

n8n должен иметь доступ к Redis. Создайте общую сеть, если её ещё нет:

```bash
docker network create vpn_n8n_shared
```

Если n8n уже запущен со своей сетью — укажите имя этой сети в `docker-compose.yml`:

```yaml
networks:
  vpn_n8n_shared:
    external: true
    name: имя_вашей_существующей_сети
```

### Шаг 4. Запустить

```bash
docker compose up -d --build
```

### Шаг 5. Проверить

```bash
docker compose ps
docker compose logs helpdesk --tail=50
```

Успешный старт выглядит так:
```
INFO: Application startup complete.
INFO: Uvicorn running on http://0.0.0.0:8000
```

### Шаг 6. Открыть панель

Откройте `http://ваш_сервер:8000` (или настроенный через nginx публичный адрес) и войдите с данными из `ADMIN_INIT_TG` / `ADMIN_INIT_PASSWORD`.

### Обновление

```bash
git pull origin main
docker compose up -d --build helpdesk
```

Схема БД обновляется автоматически при рестарте — новые колонки добавляются через `ALTER TABLE ... IF NOT EXISTS`.

> После `git pull` всегда делайте `--build` — статические файлы React копируются в Docker-образ при сборке.

---

## 7. Первый запуск и инициализация

При старте приложение автоматически:

1. **Мигрирует БД** — создаёт все таблицы, добавляет отсутствующие колонки. Безопасно для повторного запуска.
2. **Создаёт первого администратора** — если в таблице `operators` нет ни одной записи и заданы `ADMIN_INIT_TG` + `ADMIN_INIT_PASSWORD`.
3. **Синхронизирует настройки в Redis** — читает `ai_settings` и `schedule` из PostgreSQL и записывает их в Redis-ключи для n8n.
4. **Запускает фоновые задачи** — `redis_consumer` (читает входящие сообщения) и мониторинг серверов.

**Миграция с предыдущей системы (Telegram-топики):** если в БД уже есть таблицы `dialogs`, `messages` или `chat_topics` от старой системы — они автоматически переименуются в `dialogs_legacy`, `messages_legacy` и т.д. Данные не удаляются, новые таблицы создаются рядом.

### После первого входа настройте в веб-панели

1. **Настройки → AI-ассистент** — напишите системный промпт на языке ваших клиентов, настройте температуру.
2. **Настройки → Расписание** — укажите рабочие часы поддержки.
3. **Настройки → Операторы** — добавьте сотрудников.
4. **Настройки → База знаний** — загрузите `.txt`/`.md` файлы с инструкциями.

---

## 8. Настройка n8n

n8n запускается отдельно от этого docker-compose. Подключение к Redis и PostgreSQL — через Docker-сеть `vpn_n8n_shared`.

### Credentials в n8n

**Redis:**
- Host: `redis` (внутри Docker-сети) или IP сервера
- Port: `6379`

**PostgreSQL** (если n8n читает/пишет в БД напрямую):
- Host: `postgres` или IP сервера
- Port: `5432` (внутренний) / `5433` (внешний)
- Database: `vpnbot`
- User: `vpnbot`
- Password: значение `POSTGRES_PASSWORD`

### Структура воркфлоу в n8n

#### Воркфлоу 1: Входящие сообщения от пользователей

```
Telegram Trigger
    │
    ├─ Если есть файл:
    │      Скачать через Telegram API
    │      └─ POST /api/n8n/upload (с X-API-Key)
    │          └─ Сохранить url из ответа
    │
    ├─ Redis GET: vpn_bot:ai_settings  → распарсить JSON
    ├─ Redis GET: vpn_bot:schedule     → проверить рабочие часы
    │
    ├─ Если AI включён (auto_reply=true) И рабочее время:
    │      Вызвать LLM (OpenAI/Gemini) с промптом из настроек
    │      │
    │      ├─ Redis LPUSH vpn_bot:incoming:
    │      │   { "type": "ai_response", "dialog_id": "...", "message": "..." }
    │      │
    │      └─ Redis LPUSH vpn_bot:incoming:
    │          { "type": "user_message", ... все поля пользователя ... }
    │
    └─ Если AI выключен или не рабочее время:
           Redis LPUSH vpn_bot:incoming:
           { "type": "user_message", "ai_enabled": false, ... }
```

#### Воркфлоу 2: Ответы операторов → Telegram

```
Redis Subscribe: vpn_bot:messages
    │
    ├─ Если есть file_url:
    │      GET {BASE_URL}{file_url}  → скачать файл
    │      bot.sendDocument(chat_id, file)
    │
    └─ Иначе:
           bot.sendMessage(chat_id, message)
```

#### Воркфлоу 3: Закрытие диалога

```
Redis Subscribe: vpn_bot:dialog_closed
    │
    └─ bot.sendMessage(chat_id, "Ваш вопрос решён. Оцените качество поддержки:")
       [Кнопки: ⭐ ⭐⭐ ⭐⭐⭐ ⭐⭐⭐⭐ ⭐⭐⭐⭐⭐]
```

#### Воркфлоу 4: AI вкл/выкл уведомление

```
Redis Subscribe: vpn_bot:ai_toggled
    │
    ├─ ai_enabled=false → пользователю: "Соединяю вас с оператором..."
    └─ ai_enabled=true  → ничего (или подтверждение)
```

### Что n8n ДОЛЖЕН отправлять в хелпдеск

Каждый раз когда пользователь пишет в Telegram:

| Поле | Откуда брать |
|------|-------------|
| `dialog_id` | Генерировать один раз для диалога и хранить (например, `chat_id + "_" + timestamp` или UUID) |
| `chat_id` | Из Telegram-события (`message.from.id`) |
| `message` | Из Telegram-события (`message.text`) |
| `user_name` | `message.from.first_name` + `message.from.last_name` |
| `user_username` | `"@" + message.from.username` |
| `user_plan`, `user_sub_status` и т.д. | Запросить из PostgreSQL таблицы пользователей по `chat_id` |
| `ai_enabled` | Читать из таблицы `dialogs` по `dialog_id` |
| `operator_called` | `true` если пользователь нажал кнопку «Вызвать оператора» |
| `file_url` | URL из ответа `/api/n8n/upload` (если был файл) |

---

## 9. Жизненный цикл диалога

```
Статус: new → in_progress → closed
```

**`new`** — диалог только создан, ни один оператор ещё не ответил вручную.

**`in_progress`** — оператор взял диалог (начал отвечать) или произошёл handoff от AI.

**`closed`** — оператор нажал «Закрыть диалог»:
1. Хелпдеск генерирует краткое резюме через LLM (первые 20 сообщений)
2. Резюме сохраняется в `dialogs.summary`
3. В Redis публикуется событие `vpn_bot:dialog_closed`
4. Диалог остаётся в истории (доступен через «История» в панели)

### Автоматический handoff

Если AI-ответ содержит `[HANDOFF]` в начале текста И в настройках включён `handoff_enabled`:
1. Токен `[HANDOFF]` убирается из текста
2. Добавляется системное сообщение «AI передал диалог оператору»
3. `operator_called` → `true`
4. Статус → `in_progress`
5. Оператор видит диалог как требующий внимания

---

## 10. Биллинг

Операторы могут выполнять три биллинг-действия прямо из диалога:
- **Продлить подписку** — пополнить подписку пользователя
- **Докупить трафик** — добавить ГБ к текущему периоду
- **Сбросить ключ** — выдать новый VPN-ключ

### Настройка внешнего биллинг-API

```env
BILLING_API_URL=https://billing.example.com/api
BILLING_API_TOKEN=your_bearer_token
```

`HttpBillingProvider` автоматически вызывает:

| Действие | Метод | Путь | Тело |
|---------|-------|------|------|
| Продлить | POST | `/subscriptions/renew` | `{"chat_id":"...","dialog_id":"...","months":1}` |
| Трафик | POST | `/subscriptions/buy_traffic` | `{"chat_id":"...","dialog_id":"...","gb":10}` |
| Сбросить ключ | POST | `/keys/reset` | `{"chat_id":"...","dialog_id":"..."}` |

Заголовок: `Authorization: Bearer {BILLING_API_TOKEN}`

### Кастомный провайдер

Если формат API отличается — создайте свой класс в `app/billing.py`:

```python
class MyBillingProvider(BillingProvider):
    async def renew_subscription(self, chat_id: str, dialog_id: str, months: int = 1) -> BillingResult:
        # ваша логика
        return BillingResult(ok=True, message="Подписка продлена")

    async def buy_traffic(self, chat_id: str, dialog_id: str, gb: int = 10) -> BillingResult:
        ...

    async def reset_key(self, chat_id: str, dialog_id: str) -> BillingResult:
        ...
```

Зарегистрировать в `main.py`.

Если `BILLING_API_URL` не задан — автоматически используется `StubBillingProvider` (только логи, ничего не сломается).

---

## 11. Мониторинг серверов

Фоновая задача Python проверяет серверы каждые `SERVERS_CHECK_INTERVAL` секунд. n8n для этого не нужен.

### Конфигурация серверов

```env
SERVERS_MONITOR_TYPE=tcp
SERVERS_CHECK_INTERVAL=300

SERVERS=[
  {"name":"Frankfurt-01","host":"de1.vpn.example.com","port":443,"location":"DE","load_warn_pct":80},
  {"name":"Amsterdam-02","host":"nl2.vpn.example.com","port":1194,"location":"NL","load_warn_pct":75}
]
```

Поля объекта сервера:

| Поле | Обязательное | Описание |
|------|-------------|---------|
| `name` | ✅ | Отображаемое имя |
| `host` | ✅ | Хостнейм или IP |
| `port` | ✅ | TCP-порт |
| `location` | — | Код страны (DE, NL, US...) для отображения |
| `load_warn_pct` | — | Порог нагрузки в % для статуса `high` (только для `type=http`) |

### Типы мониторинга

| Тип | Как работает | Данные | Когда использовать |
|-----|-------------|--------|-------------------|
| `stub` | Случайные данные | Нагрузка, пинг, uptime | Разработка |
| `tcp` | TCP-подключение к `host:port`, измеряет задержку | Только пинг | Любой сервер, минимальные требования |
| `http` | GET `https://host:port{SERVERS_HEALTH_PATH}`, читает JSON | Нагрузка, uptime, пинг | Если на серверах есть health-эндпоинт |

**Формат ответа для `type=http`:**
```json
{"load": 42.5, "uptime": 99.9}
```
Поля опциональны — нет данных, нет отображения.

**Статусы:** `ok` (всё хорошо), `high` (нагрузка ≥ `load_warn_pct`), `down` (недоступен).

При падении сервера публикуется в Redis `vpn_bot:notifications` — n8n может отправить алерт в Telegram-канал.

---

## 12. База знаний (KB)

Позволяет n8n находить релевантные статьи для RAG-ответов AI.

### Как работает

1. Администратор загружает `.txt` или `.md` файл через **Настройки → База знаний**.
2. LLM разбивает документ на смысловые независимые чанки.
3. Каждый чанк преобразуется в эмбеддинг (OpenAI `text-embedding-3-small`).
4. Эмбеддинги и тексты сохраняются в Qdrant.
5. n8n выполняет семантический поиск через эндпоинт и получает релевантные статьи для промпта.

### Требования

- `OPENAI_API_KEY` обязателен (используется для эмбеддингов)
- Qdrant запущен (`http://qdrant:6333`)

### Использование из n8n (RAG)

n8n может запросить релевантные статьи перед вызовом LLM:

```
GET /api/kb?q=как настроить iOS&limit=3
Header: Authorization: Bearer {jwt_token}
```

Включить найденные статьи в контекст промпта.

---

## 13. Файлы: фото, документы

Telegram файлы нельзя отображать напрямую по `file_id` в браузере. Схема для файлов **от пользователя**:

```
1. Пользователь отправил фото в Telegram
2. n8n получает file_id, скачивает файл через Telegram Bot API
3. n8n POST /api/n8n/upload  (X-API-Key в заголовке)
4. Python сохраняет файл, возвращает {"url": "/api/files/abc123.jpg"}
5. n8n включает file_url в Redis-сообщение → Python сохраняет в БД
6. Оператор видит превью изображения или кнопку скачивания в браузере
```

Для файлов **от оператора**:

```
1. Оператор выбирает файл в веб-панели
2. Браузер POST /api/upload → Python возвращает URL
3. Оператор отправляет ответ с file_url
4. Redis: vpn_bot:messages с file_url и file_type
5. n8n получает событие, скачивает файл по BASE_URL + file_url
6. n8n отправляет файл пользователю в Telegram
```

---

## 14. Структура базы данных

### `dialogs` — обращения пользователей

| Столбец | Тип | Описание |
|---------|-----|---------|
| `dialog_id` | TEXT PK | Уникальный ID (генерирует n8n) |
| `chat_id` | TEXT | Telegram user ID |
| `status` | TEXT | `new` / `in_progress` / `closed` |
| `ai_enabled` | BOOL | AI отвечает в этом диалоге? |
| `operator_called` | BOOL | Пользователь запросил оператора? |
| `unread_count` | INT | Счётчик непрочитанных сообщений |
| `user_name` | TEXT | Имя пользователя |
| `user_username` | TEXT | @username в Telegram |
| `user_plan` | TEXT | Тариф (Basic, Pro, Ultimate...) |
| `user_sub_status` | TEXT | Статус подписки |
| `user_next_payment` | TEXT | Дата следующего платежа |
| `user_traffic_used` | FLOAT | Потрачено ГБ |
| `user_traffic_total` | FLOAT | Лимит ГБ |
| `last_payment_amount` | TEXT | Сумма последнего платежа |
| `last_payment_date` | TEXT | Дата последнего платежа |
| `last_message_text` | TEXT | Превью последнего сообщения |
| `last_message_time` | TIMESTAMPTZ | Время последнего сообщения |
| `summary` | TEXT | Резюме диалога (генерируется при закрытии) |
| `created_at` | TIMESTAMPTZ | Время создания |
| `updated_at` | TIMESTAMPTZ | Время последнего изменения |

### `messages` — сообщения в диалоге

| Столбец | Тип | Описание |
|---------|-----|---------|
| `id` | SERIAL PK | Автоинкремент |
| `dialog_id` | TEXT FK | Ссылка на диалог |
| `kind` | TEXT | `user` / `ai` / `operator` / `system` |
| `text` | TEXT | Текст сообщения |
| `file_id` | TEXT | Telegram file_id (legacy) |
| `file_type` | TEXT | `photo` / `document` / `voice` |
| `file_url` | TEXT | Публичный URL файла |
| `operator_name` | TEXT | Имя оператора (если kind=operator) |
| `category` | TEXT | Категория после автоклассификации |
| `created_at` | TIMESTAMPTZ | Время отправки |

### `operators` — учётные записи

| Столбец | Тип | Описание |
|---------|-----|---------|
| `id` | SERIAL PK | ID оператора |
| `name` | TEXT | Отображаемое имя |
| `tg` | TEXT | @username в Telegram |
| `tg_id` | BIGINT | Telegram user ID |
| `role` | TEXT | `admin` / `agent` |
| `online` | BOOL | Сейчас онлайн? |
| `initials` | TEXT | Инициалы (2 буквы для аватара) |
| `color` | TEXT | Цвет аватара (#RRGGBB) |
| `notif_prefs` | TEXT | JSON с настройками уведомлений |
| `password_hash` | TEXT | bcrypt-хеш пароля |

**Роли:**
- `admin` — полный доступ: управление операторами, AI-настройки, статистика, KB
- `agent` — отвечать на диалоги, загружать файлы, управлять своими уведомлениями

### `settings` — глобальные настройки

| Ключ | Значение |
|-----|---------|
| `ai_settings` | JSON: промпт, температура, auto_reply, handoff_enabled, classification_enabled |
| `schedule` | JSON: расписание по дням недели с `from`/`to` |

### `kb_articles` — база знаний

| Столбец | Тип | Описание |
|---------|-----|---------|
| `id` | TEXT PK | Slug чанка |
| `title` | TEXT | Заголовок статьи |
| `category` | TEXT | Категория |
| `keywords` | TEXT | JSON-массив ключевых слов |
| `content` | TEXT | Текст чанка |

---

## 15. REST API

### Публичные (без авторизации)

| Метод | Путь | Описание |
|-------|------|---------|
| `GET` | `/` | React SPA |
| `GET` | `/api/auth/status` | Нужна ли первичная настройка? |
| `POST` | `/api/auth/setup` | Создать первого администратора (только если операторов нет) |
| `GET` | `/api/files/{filename}` | Скачать файл |
| `POST` | `/api/n8n/upload` | Загрузка файла от n8n (требует заголовок `X-API-Key`) |

### Авторизация (Bearer token)

| Метод | Путь | Описание |
|-------|------|---------|
| `POST` | `/api/auth/login` | Получить JWT-токен |
| `GET` | `/api/auth/me` | Информация о текущем операторе |
| `PUT` | `/api/auth/password` | Сменить пароль |

### Диалоги

| Метод | Путь | Описание |
|-------|------|---------|
| `GET` | `/api/dialogs` | Список диалогов |
| `GET` | `/api/dialogs/{id}` | Диалог с историей |
| `GET` | `/api/dialogs/{id}/messages` | Сообщения диалога |
| `GET` | `/api/dialogs/{id}/history` | Прошлые диалоги этого пользователя |
| `POST` | `/api/dialogs/{id}/reply` | Отправить ответ оператора |
| `POST` | `/api/dialogs/{id}/toggle_ai` | Вкл/выкл AI |
| `POST` | `/api/dialogs/{id}/handoff` | Передать оператору вручную |
| `POST` | `/api/dialogs/{id}/close` | Закрыть диалог (генерирует резюме) |
| `POST` | `/api/dialogs/{id}/billing/{action}` | Биллинг: `renew`, `buy_traffic`, `reset_key` |

### Файлы и инфраструктура

| Метод | Путь | Описание |
|-------|------|---------|
| `POST` | `/api/upload` | Загрузить файл (оператор) |
| `GET` | `/api/servers` | Состояние VPN-серверов |
| `GET` | `/api/stats` | Статистика (только admin) |

### Операторы (только admin)

| Метод | Путь | Описание |
|-------|------|---------|
| `GET` | `/api/operators` | Список операторов |
| `POST` | `/api/operators` | Создать оператора |
| `PUT` | `/api/operators/{id}` | Обновить оператора |
| `DELETE` | `/api/operators/{id}` | Удалить оператора |
| `GET` | `/api/operators/me/notifications` | Мои настройки уведомлений |
| `PUT` | `/api/operators/me/notifications` | Сохранить настройки уведомлений |

### Настройки (только admin)

| Метод | Путь | Описание |
|-------|------|---------|
| `GET` | `/api/settings/ai` | Получить AI-настройки |
| `PUT` | `/api/settings/ai` | Сохранить AI-настройки (синхронизируется в Redis) |
| `GET` | `/api/settings/schedule` | Получить расписание |
| `PUT` | `/api/settings/schedule` | Сохранить расписание (синхронизируется в Redis) |

### База знаний (только admin)

| Метод | Путь | Описание |
|-------|------|---------|
| `GET` | `/api/kb` | Список статей KB |
| `POST` | `/api/kb/upload` | Загрузить документ (авточанкинг) |
| `DELETE` | `/api/kb/{id}` | Удалить статью |

---

## 16. WebSocket

```
WS /ws?token={jwt_token}
```

Операторы подключаются при открытии панели. Сервер рассылает события всем подключённым вкладкам:

| Тип события | Когда | Что содержит |
|-------------|-------|-------------|
| `new_message` | Новое сообщение в диалоге | dialog_id, message object |
| `dialog_updated` | Смена статуса, прочтение | dialog object |
| `new_dialog` | Создан новый диалог | dialog object |
| `operator_status` | Оператор вошёл/вышел | operator_id, online |

---

## 17. Устранение неполадок

### Сообщения не появляются в панели

1. Проверьте, что n8n и хелпдеск в одной Docker-сети:
   ```bash
   docker network inspect vpn_n8n_shared
   ```
2. Убедитесь, что n8n делает `LPUSH` (не `RPUSH`) в `vpn_bot:incoming`.
3. Проверьте логи воркера:
   ```bash
   docker compose logs helpdesk | grep -i "consumer\|redis"
   ```
4. Проверьте `REDIS_URL` в `.env` — внутри Docker должно быть `redis://redis:6379`.

### n8n не получает ответы операторов

1. n8n должен быть подписан на канал `vpn_bot:messages` через Redis Subscribe, а не читать из очереди.
2. Проверьте доступность Redis из контейнера n8n:
   ```bash
   docker exec <n8n_container> redis-cli -h redis ping
   ```

### Файлы не загружаются / не отображаются

1. Проверьте `N8N_API_KEY` — в `.env` и в заголовке `X-API-Key` в n8n.
2. Для файлов, передаваемых в Telegram, убедитесь что `BASE_URL` задан и доступен снаружи.
3. Проверьте права на папку:
   ```bash
   ls -la uploads/
   docker compose exec helpdesk ls -la app/uploads/
   ```

### AI не отвечает / ошибки классификации

1. Проверьте `OPENAI_API_KEY` или `GEMINI_API_KEY` в `.env`.
2. В панели: Настройки → AI-ассистент → убедитесь что «Автоответ» включён.
3. Логи LLM-запросов:
   ```bash
   docker compose logs helpdesk | grep -E "(LLM|classifier|summarizer|openai|gemini)"
   ```

### Ошибки базы данных при старте

1. Подождите полного запуска PostgreSQL (есть healthcheck):
   ```bash
   docker compose logs postgres
   ```
2. Проверьте `POSTGRES_PASSWORD` совпадает в `.env` и в `docker-compose.yml`.
3. Убедитесь, что `POSTGRES_HOST=postgres` (имя сервиса, не localhost).

### Панель открывается но WebSocket не подключается

1. Проверьте что nginx (если есть) настроен на проброс WebSocket:
   ```nginx
   proxy_http_version 1.1;
   proxy_set_header Upgrade $http_upgrade;
   proxy_set_header Connection "upgrade";
   ```
2. Проверьте, что JWT-токен не протух (срок — 30 дней).

### pgAdmin недоступен

- Адрес: `http://ваш_сервер:5050`
- Логин/пароль — смотри в `docker-compose.yml` (переменные `PGADMIN_DEFAULT_EMAIL` / `PGADMIN_DEFAULT_PASSWORD`)
- Подключение к БД: host=`postgres`, port=`5432`, database=`vpnbot`, user=`vpnbot`

### Посмотреть очередь Redis напрямую

```bash
# Количество сообщений в очереди
docker compose exec redis redis-cli LLEN vpn_bot:incoming

# Посмотреть первое сообщение без удаления
docker compose exec redis redis-cli LRANGE vpn_bot:incoming 0 0

# Прочитать AI-настройки
docker compose exec redis redis-cli GET vpn_bot:ai_settings
```
