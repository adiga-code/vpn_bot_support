import json
import asyncio
import redis.asyncio as aioredis
from app.telegram_bot import TelegramBot


class RedisConsumer:
    """Читает входящие сообщения от n8n из Redis"""

    def __init__(self, redis: aioredis.Redis, telegram_bot: TelegramBot):
        self.redis = redis
        self.telegram_bot = telegram_bot
        self._task = None

    async def start(self):
        self._task = asyncio.create_task(self._consume())
        print("✅ Redis consumer started")

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _consume(self):
        while True:
            try:
                result = await self.redis.blpop("vpn_bot:incoming", timeout=0)
                if not result:
                    continue

                data = json.loads(result[1])
                msg_type = data.get("type")

                if msg_type == "user_message":
                    await self.telegram_bot.send_user_message(
                        dialog_id=data["dialog_id"],
                        chat_id=str(data["chat_id"]),
                        message=data["message"],
                        ai_enabled=data.get("ai_enabled", True)
                    )
                elif msg_type == "ai_response":
                    await self.telegram_bot.send_ai_response(
                        dialog_id=data["dialog_id"],
                        chat_id=str(data["chat_id"]),
                        message=data["message"]
                    )
                else:
                    print(f"⚠️ Unknown message type: {msg_type}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"❌ Consumer error: {e}")
                await asyncio.sleep(1)
