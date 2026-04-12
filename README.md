# VPN Bot Support

Telegram-бот для поддержки VPN-пользователей. Получает сообщения от n8n через Redis, создаёт топики в Telegram-группе, маршрутизирует переписку между пользователями и менеджерами.

---

## Что делает бот

- Создаёт отдельный топик в группе для каждого диалога (`dialog_id`)
- Показывает сообщения пользователей и ответы AI в топике
- Когда менеджер отвечает в топике — пересылает ответ в n8n
- Кнопка «Переключить AI» в каждом AI-ответе — переключает статус AI для диалога
- Иконка топика меняется в зависимости от статуса AI (включён / выключён)

---

## Структура файлов

```
vpn_bot_support/
├── app/
│   ├── config.py           # Все настройки (читает из .env)
│   ├── database.py         # PostgreSQL: хранит dialog_id ↔ topic_id
│   ├── telegram_bot.py     # Telegram бот: создание топиков, отправка, кнопки
│   ├── n8n_client.py       # Публикация событий в Redis → n8n
│   └── redis_consumer.py   # Чтение входящих сообщений из Redis
├── main.py                 # Точка входа
├── Dockerfile
├── docker-compose.yml
├── .env                    # Создать из .env.example
└── .env.example
```

---

## Настройки (.env)

| Переменная | Обязательная | По умолчанию | Описание |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | — | Токен бота от @BotFather |
| `TELEGRAM_GROUP_ID` | ✅ | — | ID Telegram-группы с топиками (например `-1001234567890`) |
| `POSTGRES_PASSWORD` | ✅ | — | Пароль PostgreSQL |
| `POSTGRES_HOST` | — | `postgres` | Хост PostgreSQL (внутри Docker — имя сервиса) |
| `POSTGRES_PORT` | — | `5432` | Порт PostgreSQL |
| `POSTGRES_DB` | — | `vpnbot` | Имя базы данных |
| `POSTGRES_USER` | — | `vpnbot` | Пользователь PostgreSQL |
| `REDIS_URL` | — | `redis://localhost:6379` | URL подключения к Redis |
| `ICON_AI_ENABLED` | — | `5417915203100613993` | Custom emoji ID иконки когда AI включён |
| `ICON_AI_DISABLED` | — | `5237699328843200968` | Custom emoji ID иконки когда AI выключен |

---

## Запуск

### Docker (рекомендуется)

```bash
cp .env.example .env
# заполнить .env

docker compose up -d
```

Поднимается три контейнера:

| Контейнер | Образ | Порт на хосте |
|---|---|---|
| `telegram-webhook-bot` | python:3.11-slim | — |
| `vpn-bot-redis` | redis:7-alpine | `6380` |
| `vpn-bot-postgres` | postgres:16-alpine | `5433` |

### Локально

```bash
pip install -r requirements.txt
# в .env указать POSTGRES_HOST=localhost, REDIS_URL=redis://localhost:6379
python main.py
```

---

## Redis-очереди (интеграция с n8n)

### n8n → бот (`vpn_bot:incoming`, LPUSH)

**Сообщение пользователя** — показывает в топике:
```json
{
  "type": "user_message",
  "dialog_id": "42",
  "chat_id": "123456789",
  "message": "Привет",
  "ai_enabled": true
}
```

**Ответ AI** — показывает в топике с кнопкой переключения:
```json
{
  "type": "ai_response",
  "dialog_id": "42",
  "chat_id": "123456789",
  "message": "Чем могу помочь?"
}
```

---

### Бот → n8n

**`vpn_bot:messages`** (pub/sub) — менеджер ответил в топике:
```json
{
  "type": "manager_message",
  "dialog_id": "42",
  "chat_id": "123456789",
  "message": "Попробуйте переподключиться",
  "from": "manager"
}
```

**`vpn_bot:toggle_request`** (pub/sub) — нажата кнопка переключения AI:
```json
{
  "type": "toggle_ai",
  "dialog_id": "42",
  "chat_id": "123456789"
}
```

---

### n8n → бот (ответ на toggle)

После обработки `toggle_ai`, n8n пишет в `vpn_bot:toggle:{dialog_id}` (LPUSH):
```json
{ "ai_enabled": false }
```

Бот ждёт этот ответ **10 секунд**, затем показывает таймаут.

---

## База данных

Таблица `chat_topics` в PostgreSQL хранит маппинг диалог → топик:

```sql
CREATE TABLE chat_topics (
    id         SERIAL PRIMARY KEY,
    dialog_id  TEXT UNIQUE NOT NULL,  -- ID диалога из n8n
    chat_id    TEXT NOT NULL,          -- Telegram user ID
    topic_id   INTEGER NOT NULL,       -- ID топика в группе
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## Иконки топиков

Иконки меняются через Telegram Custom Emoji. Чтобы изменить:

1. Найти нужный эмодзи в Telegram
2. Получить его ID (через боты типа @getidsbot)
3. Обновить `ICON_AI_ENABLED` или `ICON_AI_DISABLED` в `.env`
4. Перезапустить бот: `docker compose restart telegram-webhook-bot`

---

## Подключение к PostgreSQL из n8n

PostgreSQL доступен на хосте по порту `5433`:

| Поле | Значение |
|---|---|
| Host | `172.17.0.1` (или IP сервера) |
| Port | `5433` |
| Database | значение `POSTGRES_DB` из `.env` |
| User | значение `POSTGRES_USER` из `.env` |
| Password | значение `POSTGRES_PASSWORD` из `.env` |

---

## n8n воркфлоу

Система состоит из трёх воркфлоу в n8n.

---

### 1. Main (основной воркфлоу)

Обрабатывает все входящие сообщения от пользователей и менеджеров. Содержит три независимых потока.

#### Поток 1 — Входящее сообщение от пользователя

```
Telegram Trigger (Bot 1)
    → Фильтр по id группы          # отсекает сообщения из самой admin-группы
    → Поиск диалогов пользователя  # ищет активный диалог в таблице dialogs
    → If (диалог существует?)
         ├── Да → Получить диалог
         │        → Добавить сообщение в базу (таблица messages)
         │        → Redis push → vpn_bot:incoming (user_message) — всегда
         │        → Если ИИ включена?
         │             ├── Да → Execute Workflow [AI агент]
         │             └── Нет → (всё уже отправлено)
         │
         └── Нет → Добавить диалог (создать запись в dialogs, ai_status=true)
                   → Получить данные пользователя (таблица users)
                   → Получить ключи пользователя (таблица keys)
                   → Парсинг ключей (форматирование текста)
                   → Итоговое сообщение (карточка пользователя)
                   → Redis push → vpn_bot:incoming (user_message с карточкой)
```

**Карточка нового пользователя** — первое сообщение в топике при создании диалога:
```
🆔 Telegram ID: 123456789
✅ Статус: зарегистрирован в боте
👤 Username: @username
📛 Имя: Имя
💰 Баланс: 0 ₽
🎯 Триал: 1
📅 Дата регистрации: ...

🔑 Ключи пользователя (1):
1. key_name
⏳ Истекает: 13.04.2026, 05:05
🖥 Сервер: remnawave
```

---

#### Поток 2 — Ответ менеджера из топика

```
Redis Trigger → vpn_bot:messages   # бот опубликовал сообщение менеджера
    → To JSON                       # парсинг JSON из Redis
    → Получить диалог по ID         # получить user_id из dialogs
    → Добавить в диалог сообщение   # сохранить в таблицу messages (type=manager)
    → Execute Workflow [output]     # отправить сообщение пользователю через Bot 1
```

---

#### Поток 3 — Переключение AI

```
Redis Trigger → vpn_bot:toggle_request   # кнопка нажата в топике
    → To JSON1                            # парсинг JSON из Redis
    → Получить диалог по ID1              # получить текущий ai_status
    → Обновить ai_status (!ai_status)     # инвертировать значение в dialogs
    → Redis push → vpn_bot:toggle:{dialog_id}   # ответить боту с новым статусом
```

---

### 2. Output (отправка пользователю)

Вспомогательный воркфлоу — отправляет сообщение пользователю в личку через Bot 1.

```
When Executed by Another Workflow
    Входные параметры: chat_id, message
    → Telegram node (Bot 1) → Send message to {chat_id}
```

Вызывается из:
- Main воркфлоу (поток 2) — когда менеджер ответил
- AI агент — когда AI сгенерировал ответ

---

### 3. AI агент (саб-воркфлоу)

Обрабатывает сообщение пользователя через AI и отправляет ответ.

```
When Executed by Another Workflow
    Входные параметры: message, dialog_id, chat_id, ai_enabled
    → AI Agent (GPT-4.1-mini)
         ├── Redis Chat Memory (ключ = dialog_id, окно = 10 сообщений)
         └── Qdrant Vector Store (коллекция support_docs, top-3)
              └── Embeddings OpenAI
    → Redis push → vpn_bot:incoming (ai_response) — показывает ответ в топике
    → Execute Workflow [output]                    — отправляет ответ пользователю
```

**AI агент:**
- Модель: `gpt-4.1-mini`
- Память: Redis по `dialog_id`, хранит последние 10 сообщений диалога
- База знаний: Qdrant, коллекция `support_docs` — поиск по 3 релевантных документа
- Язык: определяет автоматически, по умолчанию русский
- Системный промпт: техподдержка VPN-сервиса, инструкции по Happ, тарифы, правила эскалации

---

### Credentials в n8n

| Название | Тип | Используется в |
|---|---|---|
| `test` | Telegram API (Bot 1) | Telegram Trigger, output воркфлоу |
| `Postgres account` | PostgreSQL | dialogs, messages (БД бота) |
| `VPN bot` | PostgreSQL | users, keys (БД VPN-сервиса) |
| `Redis account` | Redis | все Redis-узлы |
| `OpenAI account` | OpenAI API | AI Agent, Embeddings |
| `Qdrant account` | Qdrant API | Vector Store |

---

### Таблицы PostgreSQL (n8n)

**`dialogs`** — диалоги пользователей:
```sql
id        -- dialog_id, используется как ключ во всей системе
user_id   -- Telegram user ID
username  -- Telegram username
ai_status -- boolean, включён ли AI для этого диалога
status    -- 'active' | другие
created_at
```

**`messages`** — история сообщений:
```sql
id
dialog_id  -- ссылка на dialogs.id
user_id
message    -- текст
type       -- 'user_message' | 'manager' | 'ai_response'
created_at
```

---

## Перезапуск и обновление

```bash
# Посмотреть логи
docker logs -f telegram-webhook-bot

# Перезапустить только бота (без пересборки)
docker compose restart telegram-webhook-bot

# Обновить код и пересобрать
git pull && docker compose up -d --build
```
