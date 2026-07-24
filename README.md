# VPN Bot Support — Helpdesk Panel

Веб-панель оператора поддержки для VPN-сервисов. Работает в связке с Telegram-ботами через n8n: n8n принимает сообщения от пользователей и передаёт их в панель через Redis, операторы отвечают через веб-интерфейс, n8n доставляет ответы обратно в Telegram.

Панель обслуживает **несколько ВПН-брендов сразу**: у каждого свой бот, своя база знаний,
свой промпт ИИ и свои диалоги, а оператор переключается между ними вкладками наверху и
видит только те бренды, к которым ему выдан доступ. Подробности —
в разделе [Мультисервисность](#мультисервисность-несколько-впн-в-одной-панели).

---

## Содержание

- [Архитектура](#архитектура)
- [Компоненты системы](#компоненты-системы)
- [Поток данных](#поток-данных)
- [n8n воркфлоу](#n8n-воркфлоу)
  - [Воркфлоу 1: Main (Основной)](#воркфлоу-1-main-основной)
  - [Воркфлоу 2: AI Agent](#воркфлоу-2-ai-agent)
  - [Воркфлоу 3: Output (Отправка пользователю)](#воркфлоу-3-output-отправка-пользователю)
- [Redis-протокол](#redis-протокол)
- [Мультисервисность (несколько ВПН в одной панели)](#мультисервисность-несколько-впн-в-одной-панели)
- [Что нужно настроить в n8n](#что-нужно-настроить-в-n8n)
- [Переменные окружения](#переменные-окружения)
- [Развёртывание](#развёртывание)
- [База данных](#база-данных)
- [Структура проекта](#структура-проекта)
- [REST API](#rest-api-краткий-справочник)

---

## Архитектура

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Telegram                                    │
│                    (пользователь пишет боту)                         │
└────────────────────────────┬────────────────────────────────────────┘
                             │  webhook
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           n8n                                        │
│                                                                      │
│   ┌────────────┐    ┌─────────────┐    ┌──────────────────────┐    │
│   │   Main     │───▶│  AI Agent   │───▶│      Output          │    │
│   │ воркфлоу   │    │  воркфлоу   │    │     воркфлоу         │    │
│   └─────┬──────┘    └─────────────┘    └──────────────────────┘    │
│         │                                          ▲                 │
│         │ LPUSH vpn_bot:incoming                   │                 │
│         │                             SUBSCRIBE vpn_bot:messages    │
└─────────┼──────────────────────────────────────────┼────────────────┘
          │                                           │
          ▼                                           │
┌─────────────────────────────────────────────────────────────────────┐
│                     Python (этот репозиторий)                        │
│                                                                      │
│  ┌──────────────────┐   ┌──────────────────┐   ┌────────────────┐  │
│  │  Redis Consumer  │   │   FastAPI / WS   │   │  n8n Client    │  │
│  │ (слушает очередь)│   │  (REST + WS API) │   │ (пуш в Redis)  │  │
│  └────────┬─────────┘   └────────┬─────────┘   └───────┬────────┘  │
│           │                      │                      │           │
│           ▼                      ▼                      │           │
│  ┌──────────────────────────────────────────┐           │           │
│  │              PostgreSQL                  │           │           │
│  │  services | operator_services |          │           │           │
│  │  dialogs | messages | operators |        │           │           │
│  │  service_settings | kb_articles          │           │           │
│  └──────────────────────────────────────────┘           │           │
│                                                          │           │
│  ┌─────────────────────┐   ┌────────────────────────┐  │           │
│  │       Qdrant        │   │   Redis (очереди)      │◀─┘           │
│  │  kb_{slug} на бренд │   │  vpn_bot:incoming      │              │
│  └─────────────────────┘   │  vpn_bot:messages:{slug}│              │
│                             │  vpn_bot:notifications: │              │
│                             │  vpn_bot:ai_toggled:    │              │
│                             │  vpn_bot:dialog_closed: │              │
│                             │  vpn_bot:billing:{slug} │              │
│                             └────────────────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
                             │
                             ▼ WebSocket
┌─────────────────────────────────────────────────────────────────────┐
│                    Браузер оператора                                  │
│              (React SPA — 3-колоночная панель)                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Компоненты системы

| Компонент | Технология | Назначение |
|-----------|-----------|------------|
| **Веб-сервер** | FastAPI + Uvicorn | REST API + WebSocket |
| **Redis Consumer** | asyncio + redis-py | Слушает очередь `vpn_bot:incoming` от n8n |
| **n8n Client** | redis-py PUBLISH | Пушит команды оператора в n8n |
| **База данных** | PostgreSQL 16 | Сервисы, диалоги, сообщения, операторы, настройки |
| **Векторная БД** | Qdrant | База знаний AI-агента, отдельная коллекция на каждый ВПН |
| **Очередь** | Redis 7 | Двунаправленный обмен с n8n |
| **Хранилище файлов** | Диск / S3 | Загрузка медиафайлов от операторов |
| **AI-классификация** | OpenAI / Gemini | Категоризация сообщений |
| **Фронтенд** | React 18 (CDN) + Tailwind | Панель оператора без сборки |

---

## Поток данных

### Входящее сообщение от пользователя

```
1. Пользователь пишет в Telegram
2. n8n: Telegram Trigger получает webhook
3. n8n: создаёт/находит диалог в n8n_dialogs (PostgreSQL)
4. n8n: если есть медиа — скачивает файл и загружает на наш сервер POST /api/n8n/upload
5. n8n: LPUSH в Redis-очередь vpn_bot:incoming (JSON с типом user_message и полем service)
6. Python: RedisConsumer читает сообщение из очереди
7. Python: upsert диалога и сохранение сообщения в БД
8. Python: WebSocket broadcast — сообщение видят операторы, имеющие доступ к этому сервису
9. Python: фоновая задача — классификация сообщения по категории
10. Python: если новый диалог — PUBLISH в vpn_bot:notifications:{slug} (уведомление операторов бренда)
11. Если ai_status=true для диалога → n8n вызывает AI Agent воркфлоу
```

### Ответ оператора пользователю

```
1. Оператор пишет ответ в веб-панели
2. Python: сохраняет сообщение оператора в БД
3. Python: n8n_client.send_manager_message() → PUBLISH в vpn_bot:messages:{slug}
4. n8n: Redis Trigger "Сообщение от менеджера" получает событие
5. n8n: парсит JSON, находит диалог, вызывает Output воркфлоу
6. Output воркфлоу: отправляет текст/фото/голос в Telegram пользователю
```

### AI-ответ

```
1. n8n AI Agent воркфлоу генерирует ответ через OpenAI
2. n8n: LPUSH в vpn_bot:incoming (тип ai_response)
3. Python: RedisConsumer обрабатывает ответ
4. Python: если в ответе есть [HANDOFF] — автоматически переключает на оператора
5. Python: сохраняет AI-сообщение в БД, WebSocket broadcast
6. n8n вызывает Output воркфлоу для доставки в Telegram
```

---

## n8n воркфлоу

В систему входят три взаимосвязанных воркфлоу.

---

### Воркфлоу 1: Main (Основной)

Главный воркфлоу запускается по Telegram webhook. Содержит несколько независимых веток (параллельные триггеры).

#### Ветка A: Входящее сообщение от пользователя

```
Telegram Trigger
    │
    ▼
Поиск диалогов пользователя
  (SELECT FROM n8n_dialogs WHERE user_id AND status='active')
    │
    ├── [диалог найден] → If: проверяем $json.id exists
    │       │ TRUE  → Получить диалог (SELECT BY id)
    │       │ FALSE → Добавить диалог (INSERT в n8n_dialogs)
    │                      └──► Получить диалог (SELECT BY id)
    │
    ▼
Switch: тип медиа (sticker | photo | voice | video | text)
    │
    ├── sticker → Edit Fields
    │               file_id   = sticker.file_id
    │               file_type = sticker
    │
    ├── photo → HTTP Request (getFile по file_id)
    │           HTTP Request (скачать файл)
    │           POST /api/n8n/upload (загрузить на наш сервер)
    │           Edit Fields1
    │               file_id   = URL нашего сервера
    │               file_type = photo
    │
    ├── voice → HTTP Request (getFile)
    │           HTTP Request (скачать)
    │           POST /api/n8n/upload
    │           Edit Fields2
    │               file_id   = URL нашего сервера
    │               file_type = voice
    │
    ├── video → HTTP Request2 (getFile)
    │           Edit Fields4
    │               file_id   = прямая ссылка Telegram
    │               file_type = video
    │
    └── text  → Edit Fields3
                    message   = message.text
                    file_type = text

    │ (все ветки сходятся)
    ▼
Добавить сообщение в базу (INSERT INTO n8n_messages)
    │
    ▼
Если ИИ включена для чата (проверка ai_status из n8n_dialogs)
    │
    ├── [ai_status = true]
    │       Redis LPUSH vpn_bot:incoming (type=user_message, ai_enabled=true)
    │       Call 'AI Agent' воркфлоу
    │
    └── [ai_status = false]
            Redis LPUSH vpn_bot:incoming (type=user_message, ai_enabled=false)
```

**Что кладётся в `vpn_bot:incoming` (user_message):**
```json
{
  "type": "user_message",
  "dialog_id": "42",
  "chat_id": "123456789",
  "message": "Не работает VPN",
  "ai_enabled": true,
  "file_id": "https://yourdomain.com/api/files/photo_abc.jpg",
  "file_type": "photo"
}
```

---

#### Ветка B: Сообщение от менеджера → пользователю

```
Redis Trigger: SUBSCRIBE vpn_bot:messages
    │
    ▼
To JSON (парсинг JSON из Redis message)
    │
    ▼
Получить диалог по ID (SELECT FROM n8n_dialogs WHERE id = parsed.dialog_id)
    │
    ▼
Добавить в диалог сообщение (INSERT INTO n8n_messages)
    │
    ▼
Call 'Output' воркфлоу
    chat_id   = n8n_dialogs.user_id
    message   = parsed.message
    file_id   = parsed.file_url
    file_type = parsed.file_type
```

---

#### Ветка C: Переключение AI

```
Redis Trigger: SUBSCRIBE vpn_bot:ai_toggled
    │
    ▼
To JSON1 → Получить диалог по ID1
    │
    ▼
UPDATE n8n_dialogs SET ai_status = !ai_status WHERE id = dialog_id
    │
    ▼
Redis LPUSH vpn_bot:toggle:{dialog_id}: {"ai_enabled": true/false}
```

**Что Python публикует в `vpn_bot:ai_toggled`:**
```json
{
  "type": "ai_toggled",
  "dialog_id": "42",
  "chat_id": "123456789",
  "ai_enabled": true
}
```

---

#### Ветка D: Уведомления операторов

```
Redis Trigger: SUBSCRIBE vpn_bot:notifications  [по умолчанию disabled]
    │
    ▼
Формат сообщения (JS Code)
    Форматирует текст по типу события:
    - new_dialog      → "💬 Новый диалог\nПользователь: @ivan"
    - operator_called → "🆘 Пользователь @ivan вызвал оператора"
    - server_down     → "🔴 Сервер недоступен: DE-1 (Frankfurt)"
    │
    ▼
Получить операторов
    SELECT tg_id FROM operators
    WHERE tg_id IS NOT NULL
      AND (notif_prefs IS NULL OR notif_prefs->>'{type}' != 'false')
    │
    ▼
Отправить операторам (Telegram sendMessage к каждому tg_id)
```

**Что Python публикует в `vpn_bot:notifications`:**
```json
{"type": "new_dialog",      "dialog_id": "42", "username": "@ivan"}
{"type": "operator_called", "dialog_id": "42", "username": "@ivan"}
{"type": "server_down",     "server_name": "DE-1", "location": "Frankfurt"}
```

---

#### Ветка E: Биллинг

```
Redis Trigger: SUBSCRIBE vpn_bot:billing  [по умолчанию disabled]
    │
    ▼
Парсинг (JS Code)
    │
    ▼
Вызов Billing API
    POST {BILLING_API_URL}/action
    Authorization: Bearer {BILLING_API_TOKEN}
    │
    ▼
Формат ответа
    Успех: "✅ Подписка продлена!" / "✅ Трафик куплен!" / "✅ Ключ сброшен!"
    Ошибка: "❌ Ошибка при выполнении: ..."
    │
    ▼
Call 'Output' воркфлоу → отправить пользователю результат
```

**Что Python публикует в `vpn_bot:billing`:**
```json
{
  "action": "renew",
  "chat_id": "123456789",
  "dialog_id": "42",
  "months": 1
}
```

Возможные значения `action`: `renew`, `buy_traffic`, `reset_key`.

---

#### Ветка F: Закрытие диалога

```
Redis Trigger: SUBSCRIBE vpn_bot:dialog_closed
    │
    ▼
To JSON2 → Получить диалог по ID3
    │
    ▼
UPDATE n8n_dialogs SET status='closed' WHERE id = dialog_id
```

**Что Python публикует в `vpn_bot:dialog_closed`:**
```json
{
  "type": "dialog_closed",
  "dialog_id": "42",
  "chat_id": "123456789"
}
```

---

### Воркфлоу 2: AI Agent

Вызывается из Main воркфлоу через `executeWorkflow` когда `ai_status = true`.

```
When Executed by Another Workflow
  Inputs: message, dialog_id, chat_id, ai_enabled, file_url, file_type
    │
    ▼
Switch: тип файла (voice | photo | text)
    │
    ├── voice → HTTP Request (скачать файл по file_url, responseFormat=file)
    │           Transcribe a recording (OpenAI Whisper)
    │           Тип аудио:
    │               analyzed = "TRANSCRIBED AUDIO TEXT: {text}\nCAPTION: {caption}"
    │
    ├── photo → HTTP Request (скачать фото, responseFormat=file)
    │           Analyze image (GPT-4o-mini vision)
    │               Промпт: подробно описать что видно на изображении
    │               Поля: тип изображения, описание, текст, детали
    │           Тип фото:
    │               analyzed = "ANALISED IMAGE TEXT: {описание}\nCAPTION: {caption}"
    │
    └── text  → Тип текст:
                    analyzed = message (без изменений)

    │ (все ветки → Приведение к 1 формату)
    ▼
Приведение к 1 формату: prompt = analyzed
    │
    ▼
Redis1: GET vpn_bot:ai_settings:{slug}
    │  Читает настройки AI из Redis (JSON):
    │  ai_model, ai_temperature, ai_prompt
    │
    ▼
Code in JavaScript: парсит ai_settings, выставляет дефолты
    ai_model       = settings.model       ?? 'gpt-4o-mini'
    ai_temperature = settings.temperature ?? 0.7
    ai_prompt      = settings.prompt      ?? ''
    │
    ▼
AI Agent (LangChain Agent)
    │  Системный промпт: ai_prompt из настроек
    │  Инструменты:
    │  ├── OpenAI Chat Model (модель из ai_settings, температура из ai_settings)
    │  ├── OpenAI Chat Model1 (gpt-4.1-mini — fallback модель)
    │  ├── Redis Chat Memory (ключ=dialog_id, окно=10 сообщений)
    │  └── Qdrant Vector Store (коллекция=kb_{slug}, top-3)
    │      Embeddings: OpenAI text-embedding-ada-002
    │      Описание инструмента: "Search VPN support knowledge base..."
    │
    ▼
Redis LPUSH vpn_bot:incoming
    {
      "type": "ai_response",
      "dialog_id": "...",
      "chat_id": "...",
      "message": "<ответ AI>",
      "ai_enabled": true
    }
    │
    ▼
Call 'Output' воркфлоу (отправить AI-ответ в Telegram)
```

**Настройки AI в Redis** (ключ `vpn_bot:ai_settings:{slug}`, устанавливается из веб-панели):
```json
{
  "enabled": true,
  "model": "gpt-4o-mini",
  "temperature": 0.7,
  "prompt": "Ты — AI-ассистент поддержки VPN-сервиса...",
  "auto_reply": true,
  "handoff_enabled": true
}
```

**Специальный маркер `[HANDOFF]`:** если AI добавляет этот маркер в ответ, Python-сторона автоматически переключает диалог на оператора (выключает AI, устанавливает `operator_called=true`, меняет статус диалога).

---

### Воркфлоу 3: Output (Отправка пользователю)

Универсальный воркфлоу для отправки любого типа контента пользователю в Telegram. Вызывается из Main и AI Agent как `executeWorkflow`.

```
When Executed by Another Workflow
  Inputs: chat_id, message, file_id, file_type
    │
    ▼
Switch: file_type
    │
    ├── "photo"   → HTTP Request (скачать файл по file_id как binary)
    │               Send a photo message
    │                   Telegram sendPhoto + binary data
    │                   caption = message
    │
    ├── "sticker" → Send a sticker
    │                   Telegram sendSticker
    │                   file = file_id (оригинальный Telegram file_id)
    │
    ├── "voice"   → HTTP Request2 (Telegram getFile по file_id)
    │               HTTP Request3 (скачать OGG по result.file_path)
    │               HTTP Request4 (POST sendVoice multipart/form-data)
    │
    └── [text/default] → Send a text message
                             Telegram sendMessage
                             parse_mode = HTML
```

> **Важно:** для фото/голоса загруженных оператором через веб-панель `file_id` содержит URL нашего сервера (`https://yourdomain.com/api/files/...`). Для стикеров от пользователей — передаётся оригинальный Telegram `file_id` напрямую.

---

## Redis-протокол

### n8n → Python (очередь `vpn_bot:incoming`)

n8n делает **LPUSH**, Python читает через **BRPOP** (блокирующее чтение с таймаутом).

**Тип `user_message`:**
```json
{
  "type": "user_message",
  "dialog_id": "42",
  "chat_id": "123456789",
  "message": "Не работает подключение",
  "ai_enabled": false,
  "file_id": "https://yourdomain.com/api/files/photo_abc.jpg",
  "file_type": "photo"
}
```

**Тип `ai_response`:**
```json
{
  "type": "ai_response",
  "dialog_id": "42",
  "chat_id": "123456789",
  "message": "Попробуйте переподключиться. [HANDOFF]",
  "ai_enabled": true
}
```

### Python → n8n (каналы PUBLISH)

Каждый ВПН-бренд крутит свою копию воркфлоу, поэтому исходящие каналы имеют
суффикс `:{slug}` — иначе каждая копия получала бы чужой трафик.

| Канал Redis | Назначение |
|------------|-----------|
| `vpn_bot:messages:{slug}` | Ответ оператора → пользователю |
| `vpn_bot:notifications:{slug}` | Уведомление операторов (new_dialog, operator_called, server_down) |
| `vpn_bot:ai_toggled:{slug}` | Включение/выключение AI для диалога |
| `vpn_bot:dialog_closed:{slug}` | Закрытие диалога |
| `vpn_bot:billing:{slug}` | Биллинговые действия (renew, buy_traffic, reset_key) |

Пока `PUBLISH_LEGACY_CHANNELS=true`, события сервиса **по умолчанию** дублируются ещё и в
старые имена без суффикса (`vpn_bot:messages` и т.д.) — так можно мигрировать воркфлоу
по одному. После миграции выключите флаг, иначе будут дубли.

**`vpn_bot:messages:{slug}` — ответ оператора:**
```json
{
  "type": "manager_message",
  "service": "nordflow",
  "dialog_id": "42",
  "chat_id": "123456789",
  "message": "Проверьте настройки подключения",
  "file_url": "https://yourdomain.com/api/files/instruction.png",
  "file_type": "photo"
}
```

> **`dialog_id` наружу — всегда внешний id**, тот самый `n8n_dialogs.id`, который прислал n8n.
> Внутри панель хранит диалоги под составным ключом `{slug}:{dialog_id}` (см. «Мультисервисность»),
> но в Redis он никогда не попадает — n8n работает со своими id как и раньше.

### Ключи SET/GET в Redis

| Ключ | Кто пишет | Кто читает | Содержимое |
|------|-----------|-----------|-----------|
| `vpn_bot:ai_settings:{slug}` | Python (Settings API) | n8n AI Agent | JSON с настройками AI этого сервиса |
| `vpn_bot:schedule:{slug}` | Python (Settings API) | Python (n8n_client) | JSON с расписанием работы этого сервиса |
| `vpn_bot:pending_notifications:{slug}` | Python | Python | Очередь уведомлений, накопленных в нерабочее время |
| `vpn_bot:toggle:{dialog_id}` | n8n | Python | `{"ai_enabled": true/false}` |

---

## Мультисервисность (несколько ВПН в одной панели)

Одна панель обслуживает несколько ВПН-брендов. У каждого свои диалоги, база знаний,
промпт ИИ, расписание и свой Telegram-бот. Оператор видит вкладки-пилюли только тех
сервисов, к которым ему выдан доступ, а рядом с названием — счётчик обращений,
требующих ответа (новые + непрочитанные).

### Как сервис попадает в систему

n8n добавляет в payload `vpn_bot:incoming` поле `service` со slug'ом бренда:

```json
{
  "type": "user_message",
  "service": "nordflow",
  "dialog_id": "42",
  "chat_id": "123456789",
  "message": "Не работает VPN",
  "ai_enabled": true
}
```

Payload без `service` относится к сервису по умолчанию — старые воркфлоу продолжают
работать без правок. Неизвестный slug логируется и отбрасывается: лучше потерять
сообщение, чем подшить его не тому бренду.

### Ключ диалога

`n8n_dialogs.id` — это последовательность внутри конкретной базы n8n. Если инстансов n8n
несколько, один и тот же id придёт от двух брендов и их переписки склеятся. Поэтому
панель хранит диалоги под составным ключом:

```
dialogs.dialog_id  = "nordflow:42"   ← внутренний ключ панели (PK)
dialogs.external_id = "42"           ← то, что знает n8n; уходит наружу в Redis
```

Наружу всегда уходит `external_id` + `service`, внутри (в БД, API, WebSocket, фронте)
ходит составной ключ. Двоеточие безопасно как разделитель: slug ограничен
`^[a-z0-9][a-z0-9_-]{1,31}$`.

### Доступ операторов

`role='admin'` даёт доступ ко всем сервисам автоматически. Агентам админ проставляет
флаги в Настройки → Операторы (таблица `operator_services`). Проверка серверная:
попытка прочитать или ответить в диалог чужого сервиса возвращает `403`, а WebSocket
рассылает события только тем вкладкам, чей оператор имеет доступ к сервису диалога.

### Изоляция данных

| Что | Как разделено |
|-----|--------------|
| Диалоги и сообщения | `dialogs.service_id`, сообщения — через `dialog_id` |
| История тикетов | Ищется в рамках сервиса: один `chat_id` может писать нескольким брендам |
| База знаний | Своя коллекция Qdrant `kb_{slug}`, `kb_articles.service_id` |
| Промпт ИИ, расписание | `service_settings (service_id, key)` |
| Redis-каналы | Суффикс `:{slug}` |
| Уведомления операторам | Свой канал на сервис + SQL-фильтр по `operator_services` |

### Миграция существующей установки

При первом запуске новой версии автоматически:

1. Создаётся сервис по умолчанию из `DEFAULT_SERVICE_SLUG` / `DEFAULT_SERVICE_NAME`.
2. Все существующие диалоги, статьи базы знаний и операторы привязываются к нему.
3. Ключи диалогов и сообщений перевыпускаются в формат `{slug}:{external_id}`
   (одной транзакцией, FK временно снимается и возвращается с `ON UPDATE CASCADE`).
4. Глобальные `ai_settings` и `schedule` переносятся в `service_settings`.

Разовые шаги защищены таблицей `schema_migrations` — повторный запуск ничего не трогает.
**Перед обновлением снимите дамп БД:** шаг 3 переписывает первичные ключи.

---

## Что нужно настроить в n8n

### 0. На каждый новый ВПН

Скопируйте воркфлоу Main и Output и поправьте в копии:

1. **Telegram credential** — свой бот бренда.
2. **Redis LPUSH `vpn_bot:incoming`** — добавьте в payload поле
   `"service": "<slug>"` (тот же slug, что в Настройки → Сервисы).
3. **Redis Trigger'ы** — переподпишите на каналы с суффиксом:
   `vpn_bot:messages:<slug>`, `vpn_bot:ai_toggled:<slug>`,
   `vpn_bot:dialog_closed:<slug>`, `vpn_bot:billing:<slug>`,
   `vpn_bot:notifications:<slug>`.
4. **AI Agent** — `Redis GET vpn_bot:ai_settings:<slug>`;
   Qdrant Vector Store → коллекция `kb_<slug>`;
   ключ Redis Chat Memory сделайте `<slug>:{dialog_id}`.
5. **Ветка уведомлений**, узел «Получить операторов» — только операторы этого бренда
   плюс все админы:
   ```sql
   SELECT o.tg_id FROM operators o
     JOIN operator_services os ON os.operator_id = o.id
     JOIN services s ON s.id = os.service_id
    WHERE s.slug = '{{ $json.service }}' AND o.tg_id IS NOT NULL
      AND (o.notif_prefs IS NULL OR o.notif_prefs::json->>'{{ $json.type }}' != 'false')
   UNION
   SELECT tg_id FROM operators WHERE role = 'admin' AND tg_id IS NOT NULL
   ```

Без шага 5 алерты одного бренда придут операторам всех остальных.

### 1. Credentials

| Credential | Тип | Где используется |
|-----------|-----|-----------------|
| **Telegram account** | Telegram API | Telegram Trigger, отправка сообщений операторам |
| **Telegram account** (бот пользователей) | Telegram API | Output воркфлоу (sendPhoto, sendSticker, sendVoice) |
| **Postgres account** | PostgreSQL | Все узлы работы с БД |
| **Redis account** | Redis | Redis Trigger, LPUSH, PUBLISH |
| **OpenAI account** | OpenAI API | AI Agent, Whisper, Vision, Embeddings |
| **Qdrant account** | Qdrant API | Qdrant Vector Store2 в AI Agent |

Redis в credentials: host = `redis`, port = `6379` (если в одной Docker-сети с n8n).

### 2. Переменные n8n (`$vars`)

В n8n → Settings → Variables:

| Переменная | Пример | Где используется |
|-----------|--------|-----------------|
| `BILLING_API_URL` | `https://billing.example.com` | Ветка Billing |
| `BILLING_API_TOKEN` | `your-token` | Ветка Billing |

### 3. Загрузка файлов на наш сервер

В HTTP Request узлах загрузки фото/голоса (Main воркфлоу) нужно добавить заголовок для авторизации:
```
X-API-Key: {значение N8N_API_KEY из .env}
```

URL загрузки: `POST https://yourdomain.com/api/n8n/upload`

### 4. Токены ботов в HTTP Request узлах

В Main воркфлоу некоторые HTTP Request узлы используют захардкоженные токены для вызова Telegram API (getFile). Замените их на актуальные токены бота:

- **HTTP Request** (getFile фото) — бот слушающий пользователей
- **HTTP Request1** (getFile голос) — тот же бот
- **HTTP Request2** (getFile видео) — тот же бот

В Output воркфлоу:
- **HTTP Request2** (getFile голос) — бот для отправки
- **HTTP Request3** (скачать голосовой файл) — тот же
- **HTTP Request4** (sendVoice) — тот же

> Один и тот же Telegram бот может использоваться для получения и отправки, или два разных — зависит от вашей схемы.

### 5. Qdrant коллекция

В AI Agent воркфлоу: `Qdrant Vector Store2` → Collection: **`kb_<slug>`** (например `kb_nordflow`).
Точное имя коллекции показано в панели: Настройки → Сервисы, колонка «База знаний».

Коллекция создаётся автоматически при первой загрузке документа
(Настройки → База знаний → выбрать сервис → Загрузить документ).

> **Важно, если вы обновляетесь со старой версии.** Раньше панель писала в коллекцию `kb`,
> а этот узел читал `support_docs` — то есть база знаний до ИИ фактически не доходила.
> Заодно проверьте модель эмбеддингов: панель использует `text-embedding-3-small`,
> и узел Embeddings в n8n должен использовать её же (не `text-embedding-ada-002`),
> иначе поиск вернёт шум. Документы после обновления нужно загрузить заново.

### 6. Включение Triggers

По умолчанию отключены (disabled):
- `Redis: Уведомления` (`vpn_bot:notifications`) — включите для Telegram-уведомлений операторам
- `Redis: Биллинг` (`vpn_bot:billing`) — включите при подключении биллингового API

---

## Переменные окружения

Создайте `.env` из шаблона:

```bash
cp .env.example .env
```

### Обязательные

| Переменная | Описание | Как получить |
|-----------|---------|-------------|
| `SECRET_KEY` | JWT-подпись (≥32 символа) | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL | Любой надёжный пароль |

### Первый администратор

| Переменная | Описание | Пример |
|-----------|---------|--------|
| `ADMIN_INIT_TG` | Telegram handle первого админа | `@myusername` |
| `ADMIN_INIT_PASSWORD` | Пароль первого админа | `Admin123!` |

Создаётся один раз при первом запуске. После создания можно оставить — повторно не создаётся если оператор уже существует.

### Сервисы (ВПН-бренды)

| Переменная | По умолчанию | Описание |
|-----------|-------------|---------|
| `DEFAULT_SERVICE_SLUG` | `default` | Идентификатор сервиса, к которому при первом запуске привязываются все существующие диалоги, статьи базы знаний и операторы |
| `DEFAULT_SERVICE_NAME` | `Основной` | Отображаемое имя этого сервиса |
| `PUBLISH_LEGACY_CHANNELS` | `true` | Пока включено, события сервиса по умолчанию дублируются в старые имена Redis-каналов без суффикса `:{slug}` — чтобы не переписывать все воркфлоу n8n разом |

Slug должен подходить под `^[a-z0-9][a-z0-9_-]{1,31}$` — он попадает в имена Redis-каналов
и коллекций Qdrant. Задавать его имеет смысл **до первого запуска**: потом он вшит в ключи
диалогов и меняться не может. Остальные сервисы добавляются из панели
(Настройки → Сервисы), env-переменные для них не нужны.

### Сеть и сервисы

| Переменная | По умолчанию | Описание |
|-----------|-------------|---------|
| `REDIS_URL` | `redis://redis:6379` | URL Redis |
| `POSTGRES_HOST` | `postgres` | Хост PostgreSQL |
| `POSTGRES_PORT` | `5432` | Порт PostgreSQL |
| `POSTGRES_DB` | `helpdesk` | Имя базы данных |
| `POSTGRES_USER` | `helpdesk` | Пользователь PostgreSQL |
| `WEB_HOST` | `0.0.0.0` | Хост uvicorn |
| `WEB_PORT` | `8000` | Порт uvicorn |

### Публичный URL и файлы

| Переменная | Описание | Пример |
|-----------|---------|--------|
| `BASE_URL` | Публичный HTTPS URL (без `/`) | `https://support.example.com` |
| `BASE_URL_PATH` | Субпуть если за reverse-proxy | `/helpdesk` (пусто если нет) |
| `UPLOADS_DIR` | Директория для загрузок | `app/uploads` |
| `N8N_API_KEY` | Статический ключ для n8n при загрузке файлов | `n8n-secret-key-12345` |

`BASE_URL` используется для формирования ссылок на файлы, которые передаются в n8n и далее в Telegram.

### S3-хранилище (опционально)

Если переменные заданы — файлы хранятся в S3 вместо диска.

| Переменная | Описание |
|-----------|---------|
| `S3_BUCKET` | Имя bucket |
| `S3_ENDPOINT_URL` | Endpoint S3-совместимого сервиса |
| `S3_ACCESS_KEY` | Access key |
| `S3_SECRET_KEY` | Secret key |
| `S3_REGION` | Регион (по умолчанию: `us-east-1`) |
| `S3_PUBLIC_URL` | CDN домен для ссылок на файлы |

### AI-провайдер

| Переменная | По умолчанию | Описание |
|-----------|-------------|---------|
| `CHAT_PROVIDER` | `openai` | Провайдер: `openai` или `gemini` |
| `OPENAI_API_KEY` | — | Ключ OpenAI (обязателен — используется для embeddings) |
| `GEMINI_API_KEY` | — | Ключ Gemini (если `CHAT_PROVIDER=gemini`) |
| `QDRANT_URL` | `http://qdrant:6333` | URL Qdrant |

### Биллинг

| Переменная | Описание | Пример |
|-----------|---------|--------|
| `BILLING_API_URL` | URL биллингового API | `https://billing.example.com` |
| `BILLING_API_TOKEN` | Bearer-токен для биллинга | `billing-secret-token` |

Если не заданы — используется `StubBillingProvider` (ничего не делает, всегда отвечает успехом).

### Мониторинг серверов

| Переменная | По умолчанию | Описание |
|-----------|-------------|---------|
| `SERVERS_MONITOR_TYPE` | `stub` | Тип: `tcp` (TCP-пинг), `http` (health endpoint), `stub` (заглушка) |
| `SERVERS` | `[]` | JSON-список серверов |
| `SERVERS_CHECK_INTERVAL` | `300` | Интервал проверки (секунды) |
| `SERVERS_HEALTH_PATH` | `/health` | Путь для HTTP-мониторинга |

Пример `SERVERS`:
```json
[
  {"name": "DE-1", "host": "de1.vpn.example.com", "port": 443, "location": "Frankfurt"},
  {"name": "NL-1", "host": "nl1.vpn.example.com", "port": 443, "location": "Amsterdam"}
]
```

---

## Развёртывание

### Быстрый старт (Docker Compose)

```bash
# 1. Клонировать репозиторий
git clone https://github.com/adiga-code/vpn_bot_support.git
cd vpn_bot_support

# 2. Создать .env
cp .env.example .env
# Отредактировать .env — заполнить SECRET_KEY, POSTGRES_PASSWORD, BASE_URL, N8N_API_KEY и т.д.

# 3. Запустить
docker compose up -d

# 4. Проверить логи
docker compose logs -f helpdesk
```

Панель доступна на `http://localhost:8000`.

### Docker Compose сервисы

| Сервис | Образ | Порт | Описание |
|--------|-------|------|---------|
| `helpdesk` | Dockerfile (python:3.11-slim) | 8000 | Основное приложение |
| `postgres` | postgres:16-alpine | 5432 | База данных |
| `redis` | redis:7-alpine | 6380→6379 | Очереди сообщений |
| `qdrant` | qdrant/qdrant | 6333, 6334 | Векторная БД для KB |
| `pgadmin` | dpage/pgadmin4:7.2 | 5050 | Веб-интерфейс к PostgreSQL |

### Подключение n8n к Redis

Если n8n запущен в отдельном docker-compose, нужна общая Docker-сеть.

В `docker-compose.yml` этого проекта уже есть секция `external_network`. Убедитесь что n8n подключён к той же сети и может достучаться до контейнера `redis` по имени хоста `redis` на порту `6379`.

Если сети нет — создайте:
```bash
docker network create n8n_network
```

### Миграции БД

Миграции применяются **автоматически** при каждом старте приложения через `ALTER TABLE IF NOT EXISTS`. Отдельно запускать ничего не нужно.

### Обновление

```bash
git pull
docker compose build helpdesk
docker compose up -d helpdesk
```

### Nginx (пример конфига)

```nginx
server {
    listen 443 ssl;
    server_name support.example.com;

    ssl_certificate     /etc/letsencrypt/live/support.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/support.example.com/privkey.pem;

    client_max_body_size 50M;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade    $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host       $host;
        proxy_set_header   X-Real-IP  $remote_addr;
    }
}
```

WebSocket (`/ws`) проксируется автоматически благодаря заголовкам `Upgrade`.

---

## База данных

### Основные таблицы (Python-сторона)

**`services`** — ВПН-бренды

| Колонка | Тип | Описание |
|---------|-----|---------|
| `id` | SERIAL PK | — |
| `slug` | TEXT UNIQUE | Идентификатор в Redis-каналах, коллекции Qdrant и ключах диалогов. Неизменяемый |
| `name` | TEXT | Отображаемое имя |
| `color` | TEXT | Цвет точки на пилюле |
| `is_default` | BOOLEAN | Сервис, к которому привязались данные при миграции; дублирует события в легаси-каналы |
| `is_active` | BOOLEAN | Выключенный сервис скрыт из панели, но данные сохраняются |

**`operator_services`** — флаги доступа (тот самый «флаг для модера»)

| Колонка | Тип | Описание |
|---------|-----|---------|
| `operator_id` | INTEGER FK | — |
| `service_id` | INTEGER FK | PK — пара колонок. Админам записи не нужны: роль даёт доступ ко всему |

**`service_settings`** — настройки на сервис

| Колонка | Тип | Описание |
|---------|-----|---------|
| `service_id` | INTEGER FK | — |
| `key` | TEXT | `ai_settings` или `schedule`; PK — пара колонок |
| `value` | TEXT (JSON) | — |

**`schema_migrations`** — отметки о применённых разовых миграциях данных

**`dialogs`** — диалоги поддержки

| Колонка | Тип | Описание |
|---------|-----|---------|
| `dialog_id` | TEXT PK | Составной ключ `{slug}:{external_id}` |
| `external_id` | TEXT | ID диалога в n8n (`n8n_dialogs.id`); уникален в паре с `service_id` |
| `service_id` | INTEGER FK | Какому ВПН-бренду принадлежит диалог |
| `chat_id` | TEXT | Telegram chat_id пользователя |
| `status` | TEXT | `new` / `in_progress` / `closed` |
| `ai_enabled` | BOOLEAN | AI активен для этого диалога |
| `operator_called` | BOOLEAN | Пользователь запросил оператора |
| `unread_count` | INTEGER | Непрочитанных сообщений |
| `user_name` | TEXT | Имя пользователя из Telegram |
| `user_username` | TEXT | @username |
| `user_plan` | TEXT | Тарифный план |
| `user_sub_status` | TEXT | Статус подписки |
| `user_next_payment` | TEXT | Дата следующей оплаты |
| `user_traffic_used` | FLOAT | Использованный трафик (ГБ) |
| `user_traffic_total` | FLOAT | Общий трафик (ГБ) |
| `last_message_text` | TEXT | Превью последнего сообщения |
| `last_message_time` | TIMESTAMPTZ | Время последнего сообщения |
| `summary` | TEXT | AI-сводка диалога (заполняется при закрытии) |
| `created_at` | TIMESTAMPTZ | — |
| `updated_at` | TIMESTAMPTZ | — |

**`messages`** — сообщения

| Колонка | Тип | Описание |
|---------|-----|---------|
| `id` | SERIAL PK | — |
| `dialog_id` | TEXT FK | Ссылка на диалог |
| `kind` | TEXT | `user` / `ai` / `operator` / `system` |
| `text` | TEXT | Текст сообщения |
| `file_id` | TEXT | URL файла |
| `file_type` | TEXT | `photo` / `voice` / `video` / `sticker` / `text` |
| `operator_name` | TEXT | Имя оператора (для kind=operator) |
| `category` | TEXT | Категория (AI-классификация) |
| `created_at` | TIMESTAMPTZ | — |

**`operators`** — сотрудники поддержки

| Колонка | Тип | Описание |
|---------|-----|---------|
| `id` | SERIAL PK | — |
| `name` | TEXT | Имя оператора |
| `tg` | TEXT | @username в Telegram |
| `tg_id` | BIGINT | Telegram user_id (для уведомлений) |
| `role` | TEXT | `admin` / `agent` |
| `online` | BOOLEAN | Есть активный WebSocket |
| `initials` | TEXT | Аббревиатура (для аватара) |
| `color` | TEXT | Цвет аватара |
| `notif_prefs` | TEXT (JSON) | Настройки уведомлений по типам |
| `password_hash` | TEXT | bcrypt хэш пароля |

**`kb_articles`** — чанки базы знаний

| Колонка | Тип | Описание |
|---------|-----|---------|
| `id` | TEXT PK | `{slug}:{chunk-slug}` — чанки разных брендов не перетирают друг друга |
| `service_id` | INTEGER FK | Какому бренду принадлежит чанк |
| `title`, `category`, `keywords`, `content` | TEXT | — |

**`settings`** — глобальная конфигурация (key-value). Настройки ИИ и расписание
переехали в `service_settings`; таблица оставлена под действительно общие ключи.

### Таблицы n8n (общие с Python)

**`n8n_dialogs`** — используется n8n для маршрутизации

| Колонка | Тип | Описание |
|---------|-----|---------|
| `id` | SERIAL PK | Совпадает с dialog_id в dialogs |
| `user_id` | BIGINT | Telegram user_id |
| `username` | TEXT | @username |
| `ai_status` | BOOLEAN | AI включён для диалога |
| `status` | TEXT | `active` / `closed` |

**`n8n_messages`** — лог сообщений для n8n (вспомогательная)

---

## Структура проекта

```
vpn_bot_support/
├── app/
│   ├── config.py          # Все переменные окружения (Pydantic Settings)
│   ├── database.py        # PostgreSQL: все запросы + автомиграции при старте
│   ├── web_server.py      # FastAPI: REST API + WebSocket endpoint
│   ├── ws_manager.py      # WebSocket broadcast (с фильтром по сервисам) + онлайн-статус
│   ├── redis_consumer.py  # Слушает vpn_bot:incoming, обрабатывает сообщения
│   ├── n8n_client.py      # PUBLISH событий в Redis → n8n
│   ├── auth.py            # bcrypt хэширование + JWT (30 дней)
│   ├── billing.py         # Биллинговый API (HttpBillingProvider или Stub)
│   ├── servers.py         # Мониторинг VPN-серверов (TCP/HTTP/Stub)
│   ├── ai_client.py       # OpenAI / Gemini wrapper
│   ├── classifier.py      # AI-классификация категории сообщения
│   ├── kb.py              # Knowledge base: chunking + embeddings → Qdrant (kb_{slug})
│   ├── summarizer.py      # AI-сводка диалога при закрытии
│   ├── storage.py         # Хранилище файлов (Local или S3)
│   └── static/
│       ├── index.html     # React SPA (Tailwind + Babel CDN, без сборки)
│       ├── components.jsx # Avatar, Icon, Toast, Badge, StatusBadge
│       ├── service_tabs.jsx # Вкладки-пилюли ВПН-сервисов + строка контекста
│       ├── dialogs.jsx    # Основной экран: список диалогов + чат + детали
│       ├── statistics.jsx # Статистика и аналитика
│       ├── servers.jsx    # Мониторинг VPN-серверов
│       └── settings.jsx   # Операторы и их доступы, сервисы, AI, расписание, KB
├── main.py                # Точка входа: asyncio.gather(web, redis_consumer, monitor)
├── requirements.txt       # Python-зависимости
├── Dockerfile             # python:3.11-slim
├── docker-compose.yml     # Полный стек (app + PG + Redis + Qdrant + pgAdmin)
└── .env.example           # Шаблон конфигурации
```

### Запуск (`main.py`)

При старте выполняется в порядке:
1. Загрузка настроек из `.env` (Pydantic Settings)
2. Инициализация пула соединений PostgreSQL
3. Автомиграции БД (idempotent `ALTER TABLE IF NOT EXISTS`)
4. Создание первого администратора (если задан `ADMIN_INIT_TG`)
5. Инициализация: Redis, WebSocket-менеджер, n8n-клиент, биллинг, мониторинг серверов
6. Параллельный запуск трёх задач через `asyncio.gather()`:
   - Uvicorn (FastAPI + WebSocket)
   - RedisConsumer (BRPOP `vpn_bot:incoming`)
   - ServerMonitor (периодическая проверка серверов)

---

## REST API (краткий справочник)

### Аутентификация

| Метод | Путь | Описание |
|-------|------|---------|
| GET | `/api/auth/status` | Нужна ли начальная настройка |
| POST | `/api/auth/setup` | Создать первого администратора |
| POST | `/api/auth/login` | Войти (tg + password) → JWT токен |
| GET | `/api/auth/me` | Текущий оператор |
| PUT | `/api/auth/password` | Сменить пароль |

JWT токен передаётся в заголовке `Authorization: Bearer <token>` или через WebSocket query `?token=<token>`.

### Сервисы

| Метод | Путь | Описание |
|-------|------|---------|
| GET | `/api/services` | Доступные мне бренды + счётчики `openCount` / `badgeCount` |
| POST | `/api/services` | Создать бренд (admin) |
| PUT | `/api/services/{id}` | Имя, цвет, вкл/выкл (admin). Slug неизменяем |
| DELETE | `/api/services/{id}` | Удалить (admin). Запрещено, если есть диалоги или это сервис по умолчанию |
| PUT | `/api/operators/{id}/services` | Проставить флаги доступа: `{"service_ids": [1,3]}` (admin) |

### Диалоги

`{id}` — составной ключ `{slug}:{external_id}`, например `nordflow:42`.
Любой из этих запросов вернёт `403`, если у оператора нет флага на сервис диалога.

| Метод | Путь | Описание |
|-------|------|---------|
| GET | `/api/dialogs?service={slug}` | Диалоги бренда; без параметра — все доступные |
| GET | `/api/dialogs/{id}` | Диалог + история сообщений |
| GET | `/api/dialogs/{id}/history` | Предыдущие тикеты этого пользователя **в этом же бренде** |
| POST | `/api/dialogs/{id}/read` | Сбросить счётчик непрочитанных |
| POST | `/api/dialogs/{id}/reply` | Ответить пользователю |
| POST | `/api/dialogs/{id}/toggle_ai` | Вкл/выкл AI для диалога |
| POST | `/api/dialogs/{id}/handoff` | Передать оператору (выкл AI) |
| POST | `/api/dialogs/{id}/close` | Закрыть диалог |
| POST | `/api/dialogs/{id}/billing/{action}` | `renew` / `buy_traffic` / `reset_key` |

### Настройки и база знаний

Параметр `service={slug}` обязателен — эти настройки хранятся на бренд.

| Метод | Путь | Описание |
|-------|------|---------|
| GET/PUT | `/api/settings/ai?service={slug}` | Промпт и параметры ИИ (PUT — admin) |
| GET/PUT | `/api/settings/schedule?service={slug}` | Расписание работы (PUT — admin) |
| GET | `/api/kb?service={slug}` | Чанки базы знаний бренда |
| POST | `/api/kb/upload?service={slug}` | Загрузить `.txt`/`.md` → чанки → `kb_{slug}` (admin) |
| DELETE | `/api/kb/{article_id}` | Удалить чанк из БД и Qdrant (admin) |
| GET | `/api/stats?days=14&service={slug}` | Статистика; без `service` — по всем доступным (admin) |

### Файлы

| Метод | Путь | Auth | Описание |
|-------|------|------|---------|
| POST | `/api/upload` | JWT Bearer | Загрузить файл (оператор → пользователю) |
| POST | `/api/n8n/upload` | X-API-Key | Загрузить файл (n8n → хранилище) |
| GET | `/api/files/{filename}` | — | Скачать файл |

### WebSocket

```
WS /ws?token=<JWT>
```

События приходящие с сервера:
```json
{"type": "new_message",      "dialog_id": "nordflow:42", "service_id": 1, "message": {...}}
{"type": "dialog_updated",   "dialog": {...}}
{"type": "new_dialog",       "dialog": {...}}
{"type": "operator_status",  "op_id": 1, "online": true}
```

События по диалогам рассылаются **только** тем вкладкам, чей оператор имеет доступ к
сервису диалога. Клиент переподключается с экспоненциальной задержкой и после
переподключения перезапрашивает `/api/dialogs` — события, пришедшие во время обрыва,
не восстанавливаются.
