from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ai_client import ChatClient

# Запасная тема: сюда попадает всё, что не подошло под список сервиса. Удалить
# её из списка нельзя — иначе у ответа модели не было бы честного «не подходит».
FALLBACK_TOPIC = "Другое"

# Темы по умолчанию. У каждого ВПН-а свой список (ai_settings.topics), его
# редактирует админ во вкладке «ИИ-настройки».
DEFAULT_TOPICS = [
    "Оплата и подписка",
    "Подключение и настройка",
    "Скорость и качество связи",
    "Отмена и возврат",
    "Технические проблемы",
    FALLBACK_TOPIC,
]
CATEGORIES = DEFAULT_TOPICS  # прежнее имя

MAX_TOPICS = 20
MAX_TOPIC_LEN = 40


def normalize_topics(topics) -> list[str]:
    """Привести список тем к рабочему виду: без пустых и дублей (без учёта
    регистра), с «Другое» в конце. Пустой ввод — темы по умолчанию. Слишком
    длинные или многочисленные темы — ValueError с текстом для админа."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for t in topics or []:
        t = " ".join(str(t).split())
        if not t or t.lower() in seen:
            continue
        if len(t) > MAX_TOPIC_LEN:
            raise ValueError(f"Тема «{t[:20]}…» длиннее {MAX_TOPIC_LEN} символов")
        seen.add(t.lower())
        cleaned.append(t)
    if not cleaned:
        return list(DEFAULT_TOPICS)
    # «Другое» всегда последней, в единственном экземпляре.
    cleaned = [t for t in cleaned if t.lower() != FALLBACK_TOPIC.lower()]
    if len(cleaned) < 1:
        return list(DEFAULT_TOPICS)
    if len(cleaned) + 1 > MAX_TOPICS:
        raise ValueError(f"Тем не больше {MAX_TOPICS} (вместе с «{FALLBACK_TOPIC}»)")
    return cleaned + [FALLBACK_TOPIC]


def _prompt(text: str, topics: list[str]) -> str:
    return (
        "Classify the following support message into exactly one category:\n"
        + "\n".join(f"- {c}" for c in topics)
        + f"\n\nMessage: {text[:500]}\n\nReply with only the category name, nothing else."
    )


async def classify_message(text: str, chat_client: "ChatClient",
                           topics: list[str] | None = None) -> str | None:
    if not text.strip():
        return None
    topics = normalize_topics(topics)
    try:
        resp = await chat_client.client.chat.completions.create(
            model=chat_client.model,
            messages=[{"role": "user", "content": _prompt(text, topics)}],
            # max_tokens, а не max_completion_tokens: в закреплённом openai==1.30.0
            # последнего параметра нет, вызов падал TypeError, который глотался
            # ниже, — и классификация не работала вовсе. Тема до 40 символов,
            # по-русски это ~25 токенов.
            max_tokens=40,
            temperature=0,
        )
        result = (resp.choices[0].message.content or "").strip().lower()
        # Точное совпадение важнее вхождения: тема «Оплата» не должна
        # перехватить ответ «Оплата и подписка».
        for t in topics:
            if result == t.lower():
                return t
        # Длинные темы первыми: «Оплата и подписка» раньше, чем «Оплата».
        for t in sorted(topics, key=len, reverse=True):
            if t.lower() in result:
                return t
        return FALLBACK_TOPIC
    except Exception as e:
        print(f"[classifier] error: {e}")
        return None
