import json
import redis.asyncio as aioredis
from app.config import Settings


class N8NClient:
    """Клиент для работы с n8n через Redis"""

    def __init__(self, settings: Settings, redis: aioredis.Redis):
        self.redis = redis

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
            print(f"❌ Error sending manager message: {e}")
            return False

    async def notify_ai_toggled(self, dialog_id: str, chat_id: str, ai_enabled: bool) -> None:
        """Уведомляем n8n об изменении AI-статуса (fire-and-forget, без ожидания ответа)."""
        try:
            await self.redis.publish("vpn_bot:ai_toggled", json.dumps({
                "type": "ai_toggled",
                "dialog_id": dialog_id,
                "chat_id": chat_id,
                "ai_enabled": ai_enabled,
            }))
        except Exception as e:
            print(f"⚠️ notify_ai_toggled error (non-critical): {e}")

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
            print(f"❌ billing action error: {e}")
            return False
