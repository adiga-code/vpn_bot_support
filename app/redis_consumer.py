import asyncio
import json

import redis.asyncio as aioredis

from app.ai_client import ChatClient
from app.classifier import classify_message
from app.database import DatabaseManager
from app.n8n_client import N8NClient
from app.web_server import _fmt_dialog, _fmt_message
from app.ws_manager import WebSocketManager


class RedisConsumer:
    """Reads inbound n8n events from the Redis queue and pushes them to the UI via WebSocket."""

    def __init__(self, redis: aioredis.Redis, db: DatabaseManager, ws: WebSocketManager, n8n: N8NClient, chat_client: ChatClient | None = None):
        self.redis = redis
        self.db = db
        self.ws = ws
        self.n8n = n8n
        self.chat_client = chat_client

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def consume(self):
        print("Redis consumer started")
        while True:
            try:
                result = await self.redis.blpop("vpn_bot:incoming", timeout=0)
                if not result:
                    continue

                data = json.loads(result[1])
                msg_type = data.get("type")
                print(f"Received {msg_type} dialog={data.get('dialog_id')}")

                if msg_type == "user_message":
                    await self._handle_user_message(data)
                elif msg_type == "ai_response":
                    await self._handle_ai_response(data)
                else:
                    print(f"Unknown type: {msg_type}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Consumer error: {e}")
                await asyncio.sleep(1)

    # ── Handlers ──────────────────────────────────────────────────────────────

    async def _handle_user_message(self, data: dict):
        dialog_id = data["dialog_id"]
        chat_id = str(data["chat_id"])
        text = data.get("message", "")
        file_id = data.get("file_id")
        file_type = data.get("file_type", "text")
        file_url = data.get("file_url")
        ai_enabled = data.get("ai_enabled", True)
        operator_called = bool(data.get("operator_called", False))

        user_info = {k: data.get(k) for k in (
            "user_name", "user_username", "user_plan", "user_sub_status",
            "user_next_payment", "user_traffic_used", "user_traffic_total",
            "user_last_payment_amount", "user_last_payment_date",
        )}

        dialog_row = await self.db.upsert_dialog(dialog_id, chat_id, ai_enabled, user_info)
        is_new = dialog_row["is_new_dialog"]

        msg_row = await self.db.save_message(
            dialog_id,
            "user",
            text if file_type == "text" else None,
            file_id=file_id if file_type != "text" else None,
            file_type=file_type if file_type != "text" else None,
            file_url=file_url,
        )
        await self.db.update_last_message(dialog_id, text or f"[{file_type}]")

        if text and file_type == "text":
            asyncio.create_task(self._classify_later(msg_row["id"], text))

        if operator_called:
            await self.db.update_operator_called(dialog_id, True)

        updated = await self.db.get_dialog(dialog_id)
        username = updated.get("user_username") or dialog_id

        await self.ws.broadcast({
            "type": "new_message",
            "dialog_id": dialog_id,
            "message": _fmt_message(msg_row),
        })

        if is_new:
            await self.ws.broadcast({"type": "new_dialog", "dialog": _fmt_dialog(updated)})
            await self.n8n.schedule_notify("new_dialog", {"dialog_id": dialog_id, "username": username})
        else:
            await self.ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)})

        if operator_called:
            await self.n8n.schedule_notify("operator_called", {"dialog_id": dialog_id, "username": username})

    async def _classify_later(self, msg_id: int, text: str):
        try:
            ai_settings = await self.db.get_setting_json("ai_settings", {})
            if not ai_settings.get("classification_enabled") or not self.chat_client:
                return
            category = await classify_message(text, self.chat_client)
            if category:
                await self.db.update_message_category(msg_id, category)
                print(f"[classifier] msg {msg_id} → {category}")
        except Exception as e:
            print(f"[classifier] background error: {e}")

    async def _handle_ai_response(self, data: dict):
        dialog_id = data["dialog_id"]
        text = data.get("message", "")

        dialog = await self.db.get_dialog(dialog_id)
        if not dialog:
            print(f"AI response for unknown dialog: {dialog_id}")
            return

        wants_handoff = "[HANDOFF]" in text
        clean_text = text.replace("[HANDOFF]", "").strip()

        if clean_text:
            msg_row = await self.db.save_message(dialog_id, "ai", clean_text)
            await self.db.update_last_message(dialog_id, f"ИИ: {clean_text}")
            updated = await self.db.get_dialog(dialog_id)
            await self.ws.broadcast({
                "type": "new_message",
                "dialog_id": dialog_id,
                "message": _fmt_message(msg_row),
            })
            await self.ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)})

        if wants_handoff and not dialog.get("operator_called"):
            ai_settings = await self.db.get_setting_json("ai_settings", {})
            if ai_settings.get("handoff_enabled", True):
                await self._auto_handoff(dialog_id, dialog)

    async def _auto_handoff(self, dialog_id: str, dialog: dict):
        print(f"[auto-handoff] dialog={dialog_id}")
        sys_row = await self.db.save_message(dialog_id, "system", "ИИ передал диалог оператору")
        await self.db.update_status(dialog_id, "in_progress")
        await self.db.update_operator_called(dialog_id, True)
        updated = await self.db.get_dialog(dialog_id)
        await self.ws.broadcast({"type": "new_message", "dialog_id": dialog_id, "message": _fmt_message(sys_row)})
        await self.ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)})
        username = updated.get("user_username") or dialog_id
        await self.n8n.schedule_notify("operator_called", {"dialog_id": dialog_id, "username": username})
