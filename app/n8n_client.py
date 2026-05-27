import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import redis.asyncio as aioredis

from app.config import Settings

if TYPE_CHECKING:
    from app.database import DatabaseManager

_DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_SCHEDULE_DEFAULTS = {
    "mon": {"enabled": True,  "from": "09:00", "to": "21:00"},
    "tue": {"enabled": True,  "from": "09:00", "to": "21:00"},
    "wed": {"enabled": True,  "from": "09:00", "to": "21:00"},
    "thu": {"enabled": True,  "from": "09:00", "to": "21:00"},
    "fri": {"enabled": True,  "from": "09:00", "to": "21:00"},
    "sat": {"enabled": False, "from": "10:00", "to": "18:00"},
    "sun": {"enabled": False, "from": "10:00", "to": "18:00"},
}


class N8NClient:
    """Publishes outbound events to n8n via Redis channels."""

    def __init__(self, settings: Settings, redis: aioredis.Redis, db: "DatabaseManager | None" = None):
        self.redis = redis
        self.db = db

    # ── Schedule helpers ──────────────────────────────────────────────────────

    async def _is_within_schedule(self) -> bool:
        if not self.db:
            return True
        schedule = await self.db.get_setting_json("schedule", _SCHEDULE_DEFAULTS)
        now = datetime.now(timezone.utc)
        day = schedule.get(_DAY_KEYS[now.weekday()], {})
        if not day.get("enabled", False):
            return False
        try:
            fh, fm = map(int, day["from"].split(":"))
            th, tm = map(int, day["to"].split(":"))
            mins = now.hour * 60 + now.minute
            return (fh * 60 + fm) <= mins < (th * 60 + tm)
        except Exception:
            return True

    async def _flush_pending(self) -> None:
        """Publish all queued off-hours notifications."""
        while True:
            item = await self.redis.lpop("vpn_bot:pending_notifications")
            if not item:
                break
            try:
                data = json.loads(item)
                event_type = data.pop("type")
                await self.notify_event(event_type, data)
                print(f"[schedule] flushed: {event_type}")
            except Exception as e:
                print(f"[schedule] flush error: {e}")

    # ── Outbound messages ─────────────────────────────────────────────────────

    async def send_manager_message(
        self,
        dialog_id: str,
        chat_id: str,
        message: str,
        file_id: str = None,
        file_type: str = None,
        file_url: str = None,
    ) -> bool:
        try:
            payload = {
                "type": "manager_message",
                "dialog_id": dialog_id,
                "chat_id": chat_id,
                "message": message,
                "from": "manager",
            }
            if file_id:
                payload["file_id"] = file_id
            if file_type:
                payload["file_type"] = file_type
            if file_url:
                payload["file_url"] = file_url
            await self.redis.publish("vpn_bot:messages", json.dumps(payload))
            return True
        except Exception as e:
            print(f"Error sending manager message: {e}")
            return False

    async def notify_dialog_closed(self, dialog_id: str, chat_id: str, operator_name: str) -> None:
        try:
            await self.redis.publish("vpn_bot:dialog_closed", json.dumps({
                "type": "dialog_closed",
                "dialog_id": dialog_id,
                "chat_id": chat_id,
                "operator_name": operator_name,
            }))
        except Exception as e:
            print(f"notify_dialog_closed error (non-critical): {e}")

    async def notify_ai_toggled(self, dialog_id: str, chat_id: str, ai_enabled: bool) -> None:
        try:
            await self.redis.publish("vpn_bot:ai_toggled", json.dumps({
                "type": "ai_toggled",
                "dialog_id": dialog_id,
                "chat_id": chat_id,
                "ai_enabled": ai_enabled,
            }))
        except Exception as e:
            print(f"notify_ai_toggled error (non-critical): {e}")

    async def notify_event(self, event_type: str, payload: dict) -> None:
        """Direct publish — bypasses schedule. Use schedule_notify for operator alerts."""
        try:
            await self.redis.publish("vpn_bot:notifications", json.dumps({
                "type": event_type, **payload,
            }))
        except Exception as e:
            print(f"notify_event error (non-critical): {e}")

    async def schedule_notify(self, event_type: str, payload: dict) -> None:
        """Schedule-aware notification: queues during off-hours, flushes at day start."""
        try:
            if not await self._is_within_schedule():
                await self.redis.rpush("vpn_bot:pending_notifications", json.dumps({
                    "type": event_type, **payload,
                }))
                print(f"[schedule] queued {event_type} (outside working hours)")
                return
            await self._flush_pending()
            await self.notify_event(event_type, payload)
        except Exception as e:
            print(f"schedule_notify error (non-critical): {e}")

    # ── Direct user messaging (via vpn_bot:outgoing → n8n → Telegram) ──────────

    async def send_to_user(self, chat_id: str, text: str, keyboard: list = None) -> bool:
        """Публикует событие в vpn_bot:outgoing — n8n подхватывает и отправляет в Telegram."""
        try:
            payload = {"type": "send_to_user", "chat_id": chat_id, "text": text}
            if keyboard:
                payload["keyboard"] = keyboard
            await self.redis.rpush("vpn_bot:outgoing", json.dumps(payload, ensure_ascii=False))
            return True
        except Exception as e:
            print(f"send_to_user error: {e}")
            return False

    async def send_operator_button(self, chat_id: str, dialog_id: str) -> bool:
        keyboard = [[{"text": "👨‍💼 Позвать оператора", "callback_data": f"call_op:{dialog_id}"}]]
        return await self.send_to_user(chat_id, "Нужна помощь живого оператора? 👇", keyboard)

    async def send_rating_request(self, chat_id: str, dialog_id: str, text: str = "Оцените качество поддержки:") -> bool:
        stars = ["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"]
        keyboard = [[
            {"text": s, "callback_data": f"rate:{dialog_id}:{i + 1}"}
            for i, s in enumerate(stars)
        ]]
        return await self.send_to_user(chat_id, text, keyboard)

    async def send_billing_action(self, dialog_id: str, chat_id: str, action: str) -> bool:
        try:
            await self.redis.publish("vpn_bot:billing", json.dumps({
                "type": "billing_action",
                "dialog_id": dialog_id,
                "chat_id": chat_id,
                "action": action,
            }))
            return True
        except Exception as e:
            print(f"Billing action error: {e}")
            return False
