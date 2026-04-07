import json
import redis.asyncio as aioredis
from app.config import Settings


class N8NClient:
    """Клиент для работы с n8n через Redis"""

    def __init__(self, settings: Settings, redis: aioredis.Redis):
        self.redis = redis

    async def send_manager_message(self, chat_id: str, message: str) -> bool:
        try:
            await self.redis.publish("vpn_bot:outgoing", json.dumps({
                "type": "manager_message",
                "chat_id": chat_id,
                "message": message,
                "from": "manager"
            }))
            return True
        except Exception as e:
            print(f"❌ Error sending to Redis: {e}")
            return False

    async def toggle_ai_status(self, chat_id: str) -> dict:
        print(f"🔄 Toggle AI for chat_id: {chat_id}")
        try:
            await self.redis.publish("vpn_bot:outgoing", json.dumps({
                "type": "toggle_ai",
                "chat_id": chat_id
            }))

            result = await self.redis.blpop(f"vpn_bot:toggle:{chat_id}", timeout=10)

            if not result:
                return {"error": "Таймаут: n8n не ответил за 10 секунд"}

            data = json.loads(result[1])

            if "ai_enabled" not in data:
                return {"error": "n8n не вернул поле 'ai_enabled'"}

            if not isinstance(data["ai_enabled"], bool):
                return {"error": "Неверный тип данных в ответе n8n"}

            print(f"✅ AI toggled: {data['ai_enabled']}")
            return {"ai_enabled": data["ai_enabled"]}

        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return {"error": f"{type(e).__name__}: {str(e)}"}
