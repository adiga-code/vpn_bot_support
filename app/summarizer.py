from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ai_client import ChatClient

_PROMPT = (
    "Дай одну короткую фразу (до 8 слов) описывающую суть обращения пользователя в поддержку VPN-сервиса. "
    "Только суть проблемы или вопроса, без вводных слов. "
    "На русском языке.\n\nДиалог:\n{dialog}\n\nОтвет:"
)


async def summarize_dialog(messages: list[dict], chat_client: "ChatClient") -> str | None:
    if not messages or not chat_client:
        return None
    lines = []
    for m in messages[:20]:
        role = {"user": "Пользователь", "ai": "ИИ", "operator": "Оператор"}.get(m["kind"], m["kind"])
        lines.append(f"{role}: {m['text'][:200]}")
    dialog_text = "\n".join(lines)
    try:
        resp = await chat_client.client.chat.completions.create(
            model=chat_client.model,
            messages=[{"role": "user", "content": _PROMPT.format(dialog=dialog_text)}],
            max_completion_tokens=30,
            temperature=0,
        )
        return resp.choices[0].message.content.strip().strip('"').strip("'")
    except Exception as e:
        print(f"[summarizer] error: {e}")
        return None
