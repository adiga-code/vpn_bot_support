import json
import asyncio
import redis.asyncio as aioredis

from app.database import DatabaseManager
from app.ws_manager import WebSocketManager
from app.web_server import _fmt_dialog, _fmt_message


class RedisConsumer:
    """Читает входящие сообщения от n8n из Redis и транслирует в веб-интерфейс"""

    def __init__(self, redis: aioredis.Redis, db: DatabaseManager, ws: WebSocketManager):
        self.redis = redis
        self.db = db
        self.ws = ws

    async def consume(self):
        print("✅ Redis consumer started")
        while True:
            try:
                result = await self.redis.blpop("vpn_bot:incoming", timeout=0)
                if not result:
                    continue

                data = json.loads(result[1])
                msg_type = data.get("type")
                print(f"📨 {msg_type} dialog={data.get('dialog_id')}")

                if msg_type == "user_message":
                    await self._handle_user_message(data)
                elif msg_type == "ai_response":
                    await self._handle_ai_response(data)
                else:
                    print(f"⚠️ Unknown type: {msg_type}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"❌ Consumer error: {e}")
                await asyncio.sleep(1)

    async def _handle_user_message(self, data: dict):
        dialog_id = data["dialog_id"]
        chat_id = str(data["chat_id"])
        text = data.get("message", "")
        file_id = data.get("file_id")
        file_type = data.get("file_type", "text")
        file_url = data.get("file_url")  # URL если n8n уже скачал файл
        ai_enabled = data.get("ai_enabled", True)

        user_info = {k: data.get(k) for k in (
            "user_name", "user_username", "user_plan", "user_sub_status",
            "user_next_payment", "user_traffic_used", "user_traffic_total",
            "user_last_payment_amount", "user_last_payment_date",
        )}

        dialog_row = await self.db.upsert_dialog(dialog_id, chat_id, ai_enabled, user_info)
        is_new = dialog_row["unread_count"] == 1

        msg_row = await self.db.save_message(
            dialog_id,
            "user",
            text if file_type == "text" else None,
            file_id=file_id if file_type != "text" else None,
            file_type=file_type if file_type != "text" else None,
            file_url=file_url,
        )
        await self.db.update_last_message(dialog_id, text or f"[{file_type}]")

        updated = await self.db.get_dialog(dialog_id)
        if is_new:
            await self.ws.broadcast({"type": "new_dialog", "dialog": _fmt_dialog(updated)})
        else:
            await self.ws.broadcast({"type": "new_message", "dialog_id": dialog_id, "message": _fmt_message(msg_row)})
            await self.ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)})

    async def _handle_ai_response(self, data: dict):
        dialog_id = data["dialog_id"]
        text = data.get("message", "")

        dialog = await self.db.get_dialog(dialog_id)
        if not dialog:
            print(f"⚠️ AI response for unknown dialog: {dialog_id}")
            return

        msg_row = await self.db.save_message(dialog_id, "ai", text)
        await self.db.update_last_message(dialog_id, f"ИИ: {text}")

        updated = await self.db.get_dialog(dialog_id)
        await self.ws.broadcast({"type": "new_message", "dialog_id": dialog_id, "message": _fmt_message(msg_row)})
        await self.ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)})
