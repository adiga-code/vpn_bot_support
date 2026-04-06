# 🤖 VPN Bot Support

Telegram-бот поддержки VPN-пользователей. Связывает n8n с Telegram через Redis: создаёт топики в группе, маршрутизирует сообщения между менеджерами и пользователями, управляет AI-агентом.

## 🏗️ Архитектура

```
n8n ──LPUSH──→ Redis (vpn_bot:incoming) ──BLPOP──→ Bot → Telegram
n8n ──BRPOP──← Redis (vpn_bot:outgoing) ←──LPUSH──  Bot ← Telegram
```

## 📁 Структура проекта

```
vpn_bot_support/
├── app/
│   ├── config.py              # Настройки из .env
│   ├── database.py            # SQLite: маппинг chat_id ↔ topic_id
│   ├── telegram_bot.py        # Telegram бот (aiogram)
│   ├── n8n_client.py          # Отправка в Redis → n8n
│   └── redis_consumer.py      # Чтение из Redis ← n8n
├── main.py                    # Точка входа
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── .env                       # Создать вручную из .env.example
```

## 🚀 Запуск

### 1. Создать .env

```bash
cp .env.example .env
# Заполнить своими данными
```

### 2. Запустить через Docker

```bash
docker-compose up -d
```

Поднимается три сервиса:
- **telegram-bot** — сам бот
- **redis** — очередь сообщений между ботом и n8n
- **postgres** — для n8n (или других нужд)

### 3. Локальный запуск (без Docker)

```bash
pip install -r requirements.txt
python main.py
```

## ⚙️ Настройка Telegram

1. Создать бота через [@BotFather](https://t.me/BotFather), получить токен
2. Создать группу, включить топики: Настройки → Topics → Enable
3. Добавить бота в группу как администратора
4. Получить ID группы (через [@userinfobot](https://t.me/userinfobot))

## 📨 Очереди Redis

### n8n → бот (`vpn_bot:incoming`)

Сообщение пользователя:
```json
{ "type": "user_message", "chat_id": "123", "message": "Привет", "ai_enabled": true }
```

Ответ AI:
```json
{ "type": "ai_response", "chat_id": "123", "message": "Чем могу помочь?" }
```

### Бот → n8n (`vpn_bot:outgoing`)

Сообщение менеджера:
```json
{ "type": "manager_message", "chat_id": "123", "message": "Ответ менеджера", "from": "manager" }
```

Переключение AI:
```json
{ "type": "toggle_ai", "chat_id": "123" }
```

### Ответ на toggle (`vpn_bot:toggle:{chat_id}`)

n8n пишет сюда ответ после обработки toggle_ai:
```json
{ "ai_enabled": true }
```

## 🗄️ База данных

**SQLite** (`bot.db`) — хранит маппинг chat_id ↔ topic_id:

```sql
CREATE TABLE chat_topics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     TEXT UNIQUE NOT NULL,
    topic_id    INTEGER NOT NULL,
    topic_name  TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**PostgreSQL** — доступен в docker-compose для n8n или расширения функциональности.

## 🔄 Логика работы

**Входящий поток (n8n → Telegram):**
1. n8n кладёт сообщение в `vpn_bot:incoming`
2. Бот читает, создаёт топик (если нет) и отправляет сообщение в группу
3. Иконка топика отражает текущий статус AI

**Исходящий поток (Telegram → n8n):**
1. Менеджер пишет в топик → бот кладёт в `vpn_bot:outgoing`
2. Нажатие кнопки "Переключить AI" → бот кладёт toggle-запрос в `vpn_bot:outgoing` и ждёт ответа в `vpn_bot:toggle:{chat_id}` (таймаут 10с)
