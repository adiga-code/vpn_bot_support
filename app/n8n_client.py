import json

import redis.asyncio as aioredis

from app.config import Settings


class N8NClient:
    """Publishes outbound events to n8n via Redis channels."""

    def __init__(self, settings: Settings, redis: aioredis.Redis):
        # settings kept for future use (e.g. channel name overrides)
        self.redis = redis

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
        """Fire-and-forget: publish a notification event for n8n to deliver via Telegram."""
        try:
            await self.redis.publish("vpn_bot:notifications", json.dumps({
                "type": event_type, **payload,
            }))
        except Exception as e:
            print(f"notify_event error (non-critical): {e}")

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
