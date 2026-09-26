"""Загрузка выгрузки старых переписок (см. history_export) в панель.

Каждый чат становится одним закрытым тикетом «<префикс><chat_id>-0» с
исходными датами сообщений. Когда клиент напишет снова, resolve_open_dialog
заведёт ему новый тикет как обычно — всё начинается с чистого листа, а старая
переписка видна в «Обращениях».

Повторная загрузка того же (или более свежего) файла безопасна: чат, у
которого уже есть импортированный тикет, пропускается. Сообщения, которые
клиент писал уже при панели, не дублируются — они есть в её тикетах.
"""
from datetime import datetime, timezone

from app.history_export import HISTORY_FORMAT


def _parse_date(value) -> datetime | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _messages(raw: list) -> list[dict]:
    out = []
    for m in raw or []:
        if not isinstance(m, dict):
            continue
        text = str(m.get("text") or "").strip()
        date = _parse_date(m.get("date"))
        if not text or not date:
            continue
        kind = "operator" if m.get("from") == "operator" else "user"
        out.append({"kind": kind, "text": text, "date": date})
    out.sort(key=lambda m: m["date"])
    return out


class HistoryImporter:
    def __init__(self, db):
        self.db = db

    async def run(self, service: dict, payload: dict) -> dict:
        if not isinstance(payload, dict) or payload.get("format") != HISTORY_FORMAT:
            raise ValueError("Это не файл выгрузки истории панели")
        chats = payload.get("chats")
        if not isinstance(chats, list):
            raise ValueError("В файле нет списка чатов")
        account = str(payload.get("account") or "") or None

        imported = skipped = messages = 0
        for chat in chats:
            if not isinstance(chat, dict) or not str(chat.get("chat_id") or "").strip():
                skipped += 1
                continue
            msgs = _messages(chat.get("messages"))
            if not msgs:
                skipped += 1
                continue
            chat = {**chat, "chat_id": str(chat["chat_id"]).strip()}
            count = await self.db.import_closed_dialog(service, chat, msgs, account)
            if count:
                imported += 1
                messages += count
            else:
                skipped += 1
        return {"ok": True, "imported": imported, "skipped": skipped, "messages": messages}
