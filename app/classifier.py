from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ai_client import ChatClient

CATEGORIES = [
    "Оплата и подписка",
    "Подключение и настройка",
    "Скорость и качество связи",
    "Отмена и возврат",
    "Технические проблемы",
    "Другое",
]

_PROMPT = (
    "Classify the following support message into exactly one category:\n"
    + "\n".join(f"- {c}" for c in CATEGORIES)
    + "\n\nMessage: {text}\n\nReply with only the category name, nothing else."
)


async def classify_message(text: str, chat_client: "ChatClient") -> str | None:
    if not text.strip():
        return None
    try:
        resp = await chat_client.client.chat.completions.create(
            model=chat_client.model,
            messages=[{"role": "user", "content": _PROMPT.format(text=text[:500])}],
            max_completion_tokens=20,
            temperature=0,
        )
        result = resp.choices[0].message.content.strip()
        for cat in CATEGORIES:
            if cat.lower() in result.lower():
                return cat
        return "Другое"
    except Exception as e:
        print(f"[classifier] error: {e}")
        return None
