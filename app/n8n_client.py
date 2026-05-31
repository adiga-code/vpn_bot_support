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
    """All outbound events go to a single durable queue: vpn_bot:outgoing.
    n8n reads with blpop and routes by the `type` field.

    Message types:
      manager_message  — operator reply to user (text/file)
      operator_notify  — notification to the operator group (event field varies)
      send_to_user     — proactive message to user, optional inline keyboard
      billing_action   — billing command for user
    """

    def __init__(self, settings: Settings, redis: aioredis.Redis, db: "DatabaseManager | None" = None):
        self.redis = redis
        self.db = db

    # ── Core push ─────────────────────────────────────────────────────────────

    async def _push(self, payload: dict) -> bool:
        try:
            await self.redis.rpush("vpn_bot:outgoing", json.dumps(payload, ensure_ascii=False))
            await self.redis.publish("vpn_bot:signal", "1")
            return True
        except Exception as e:
            print(f"[n8n] push error: {e}")
            return False

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

    # ── Operator notifications ─────────────────────────────────────────────────

    async def notify_event(self, event_type: str, payload: dict) -> None:
        """Direct push — bypasses schedule. Use schedule_notify for operator alerts."""
        await self._push({"type": "operator_notify", "event": event_type, **payload})

    async def schedule_notify(self, event_type: str, payload: dict) -> None:
        """Schedule-aware: queues off-hours, flushes at start of working day."""
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

    # ── Manager → User ────────────────────────────────────────────────────────

    async def send_manager_message(
        self,
        dialog_id: str,
        chat_id: str,
        message: str,
        file_id: str = None,
        file_type: str = None,
        file_url: str = None,
    ) -> bool:
        payload = {
            "type": "manager_message",
            "dialog_id": dialog_id,
            "chat_id": chat_id,
            "message": message,
        }
        if file_id:
            payload["file_id"] = file_id
        if file_type:
            payload["file_type"] = file_type
        if file_url:
            payload["file_url"] = file_url
        return await self._push(payload)

    async def notify_dialog_closed(self, dialog_id: str, chat_id: str, operator_name: str) -> None:
        await self._push({
            "type": "operator_notify",
            "event": "dialog_closed",
            "dialog_id": dialog_id,
            "chat_id": chat_id,
            "operator_name": operator_name,
        })

    async def notify_ai_toggled(self, dialog_id: str, chat_id: str, ai_enabled: bool) -> None:
        await self._push({
            "type": "operator_notify",
            "event": "ai_toggled",
            "dialog_id": dialog_id,
            "chat_id": chat_id,
            "ai_enabled": ai_enabled,
        })

    # ── Direct user messaging ─────────────────────────────────────────────────

    async def send_to_user(self, chat_id: str, text: str, keyboard: list = None) -> bool:
        payload = {"type": "send_to_user", "chat_id": chat_id, "text": text}
        if keyboard:
            payload["keyboard"] = keyboard
        return await self._push(payload)

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

    # ── Billing ───────────────────────────────────────────────────────────────

    async def send_billing_action(self, dialog_id: str, chat_id: str, action: str) -> bool:
        return await self._push({
            "type": "billing_action",
            "dialog_id": dialog_id,
            "chat_id": chat_id,
            "action": action,
        })
