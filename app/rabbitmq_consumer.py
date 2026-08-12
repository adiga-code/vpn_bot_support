import asyncio
import json

import aio_pika
import aio_pika.abc

from app.ai_client import ChatClient
from app.classifier import classify_message
from app.database import DatabaseManager
from app.n8n_client import N8NClient
from app.routing import RoutingEngine
from app.serializers import fmt_dialog as _fmt_dialog, fmt_message as _fmt_message
from app.ws_manager import WebSocketManager

QUEUE_INCOMING = "vpn_bot.incoming"


class RabbitMQConsumer:
    """Reads inbound n8n events from RabbitMQ and pushes them to the UI via WebSocket."""

    def __init__(
        self,
        rmq: aio_pika.abc.AbstractRobustConnection,
        db: DatabaseManager,
        ws: WebSocketManager,
        n8n: N8NClient,
        routing: RoutingEngine,
        chat_client: ChatClient | None = None,
    ):
        self._rmq = rmq
        self.db = db
        self.ws = ws
        self.n8n = n8n
        self.routing = routing
        self.chat_client = chat_client

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def consume(self):
        print("RabbitMQ consumer started")
        channel = await self._rmq.channel()
        await channel.set_qos(prefetch_count=1)
        queue = await channel.declare_queue(QUEUE_INCOMING, durable=True)

        async with queue.iterator() as q_iter:
            async for message in q_iter:
                async with message.process(ignore_processed=True):
                    try:
                        raw = message.body
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError as je:
                            preview = raw[:200].decode("utf-8", errors="replace")
                            print(f"Consumer JSON error: {je} | body preview: {preview!r}")
                            continue
                        msg_type = data.get("type")
                        print(f"Received {msg_type} dialog={data.get('dialog_id')}")

                        if msg_type == "user_message":
                            await self._handle_user_message(data)
                        elif msg_type == "ai_response":
                            await self._handle_ai_response(data)
                        elif msg_type == "callback":
                            await self._handle_callback(data)
                        elif msg_type == "delivery_confirmation":
                            await self._handle_delivery_confirmation(data)
                        else:
                            print(f"Unknown type: {msg_type}")
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        print(f"Consumer error: {e}")

    # ── Handlers ──────────────────────────────────────────────────────────────

    async def _resolve_service(self, data: dict) -> dict | None:
        """Сервис (ВПН) входящего события.

        Основной способ — `business_id`: Telegram присылает его с каждым
        сообщением из аккаунта поддержки, к которому подключён бот, и в панели
        он записан в карточке сервиса. Поэтому воркфлоу n8n один на всех и
        ничего про сервисы не знает.

        Дальше — `service` со слагом, как в старых воркфлоу; если нет и его,
        событие относится к первому (мигрированному) сервису. Неизвестный
        business_id или слаг — сообщение отбрасывается: свалить чужой тикет в
        первый попавшийся ВПН хуже, чем не принять его вовсе.
        """
        business_id = str(data.get("business_id")
                          or data.get("business_connection_id") or "").strip()
        if business_id:
            service = await self.db.get_service_by_business_id(business_id)
            if not service:
                print(f"[consumer] неизвестный business_id '{business_id}' — "
                      f"событие отброшено; впишите его в карточку сервиса")
            return service

        slug = (data.get("service") or "").strip().lower()
        if not slug:
            services = await self.db.get_services()
            return services[0] if services else None
        service = await self.db.get_service_by_slug(slug)
        if not service:
            print(f"[consumer] неизвестный сервис '{slug}' — событие отброшено")
        return service

    @staticmethod
    def _qualify(service: dict, dialog_id, chat_id=None) -> str:
        """dialog_id из n8n → глобально уникальный ключ. Префикс разводит
        идентификаторы независимых инстансов n8n, которые могут выдать
        одинаковые номера; у мигрированного сервиса он пустой.

        Если n8n прислал пустой или нулевой идентификатор — а так бывает, когда
        колонка `n8n_dialogs.id` не автоинкрементная и каждая вставка получает
        один и тот же ноль, — ключ строится от chat_id. Иначе все клиенты
        сервиса слились бы в один тикет: `dialogs.dialog_id` первичный ключ, и
        upsert перезаписал бы чужую строку вместе с chat_id.
        """
        prefix = service["dialog_id_prefix"]
        raw = str(dialog_id if dialog_id is not None else "").strip()
        try:
            usable = bool(raw) and int(float(raw)) > 0
        except ValueError:
            usable = bool(raw)          # нечисловой, но непустой — доверяем n8n
        if not usable:
            if chat_id is None:
                raise ValueError("dialog_id пустой, и chat_id не из чего взять")
            print(f"[consumer] n8n прислал dialog_id={raw!r} — ключ построен от "
                  f"chat_id; проверьте, что n8n_dialogs.id автоинкрементный")
            raw = f"chat_{chat_id}"
        return raw if not prefix or raw.startswith(prefix) else prefix + raw

    async def _handle_user_message(self, data: dict):
        service = await self._resolve_service(data)
        if not service:
            return
        chat_id = str(data["chat_id"])
        dialog_id = self._qualify(service, data.get("dialog_id"), chat_id)
        text = data.get("message", "")
        file_id = data.get("file_id")
        file_type = data.get("file_type", "text")
        file_url = data.get("file_url")
        # n8n sometimes puts the uploaded URL into file_id instead of file_url
        if not file_url and file_id and str(file_id).startswith("http"):
            file_url, file_id = file_id, None
        raw_ai = data.get("ai_enabled", True)
        if isinstance(raw_ai, bool):
            ai_enabled = raw_ai
        elif isinstance(raw_ai, str):
            ai_enabled = raw_ai.lower() not in ("false", "0", "inactive", "disabled", "no", "off")
        else:
            ai_enabled = bool(raw_ai)
        operator_called = bool(data.get("operator_called", False))

        user_info = {k: data.get(k) for k in (
            "user_name", "user_username", "user_plan", "user_sub_status",
            "user_next_payment", "user_traffic_used", "user_traffic_total",
            "user_last_payment_amount", "user_last_payment_date",
            "user_photo_url",
        )}

        dialog_row = await self.db.upsert_dialog(
            dialog_id, chat_id, service["id"], ai_enabled, user_info
        )
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
            asyncio.create_task(self._classify_later(msg_row["id"], text, service["id"]))

        if operator_called:
            await self.db.update_operator_called(dialog_id, True)

        if is_new:
            await self.db.sync_n8n_dialog_status(chat_id, "active", {
                "service_slug": service["slug"],
                "business_connection_id": service.get("business_connection_id") or "",
            })

        updated = await self.db.get_dialog(dialog_id)
        username = updated.get("user_username") or dialog_id
        service_id = service["id"]

        await self.ws.broadcast({
            "type": "new_message",
            "dialog_id": dialog_id,
            "message": _fmt_message(msg_row),
        }, service_id)

        if is_new:
            await self.ws.broadcast({"type": "new_dialog", "dialog": _fmt_dialog(updated)}, service_id)
            await self.n8n.schedule_notify(
                "new_dialog", {"dialog_id": dialog_id, "username": username}, updated
            )
        else:
            await self.ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)}, service_id)
        await self.routing.emit_counts()

        # ── Routing ──
        # AI dialogs stay in the «ИИ» section unassigned — no eager pre-assign.
        if operator_called and updated["status"] == "ai":
            # the client asked for a human → escalate (notifies operator_called)
            await self.routing.handoff_from_ai(dialog_id)
        elif updated["status"] == "ai" and await self.routing.maybe_escalate_by_keywords(updated, text):
            # deterministic escalation by stop-words («позови оператора») —
            # fires even when the AI model fails to emit [HANDOFF]
            pass
        else:
            if operator_called:
                await self.n8n.schedule_notify(
                    "operator_called", {"dialog_id": dialog_id, "username": username}, updated
                )
            if is_new and updated["status"] == "queue":
                # AI disabled on the bot side → route straight to operators
                await self.routing.assign_or_queue(dialog_id)
            elif not is_new:
                # scenario 3/5: a client reply wakes a waiting ticket
                await self.routing.on_client_message(updated)

        automation = await self.db.get_setting_json("automation", {}, service_id)
        if automation.get("operator_button_enabled") and not operator_called:
            n = int(automation.get("operator_button_after_msgs") or 3)
            count = await self.db.get_user_message_count(dialog_id)
            if count == n:
                asyncio.create_task(self.n8n.send_operator_button(chat_id, dialog_id, updated))

    async def _classify_later(self, msg_id: int, text: str, service_id: int):
        try:
            ai_settings = await self.db.get_setting_json("ai_settings", {}, service_id)
            if not ai_settings.get("classification_enabled") or not self.chat_client:
                return
            category = await classify_message(text, self.chat_client)
            if category:
                await self.db.update_message_category(msg_id, category)
                print(f"[classifier] msg {msg_id} → {category}")
        except Exception as e:
            print(f"[classifier] background error: {e}")

    async def _handle_ai_response(self, data: dict):
        service = await self._resolve_service(data)
        if not service:
            return
        # chat_id тот же, что и во входящем: ИИ-агент кладёт его в ai_response,
        # поэтому при нулевом dialog_id ответ попадёт в тот же тикет.
        dialog_id = self._qualify(service, data.get("dialog_id"), data.get("chat_id"))
        text = data.get("message", "")

        dialog = await self.db.get_dialog(dialog_id)
        if not dialog:
            print(f"AI response for unknown dialog: {dialog_id}")
            return

        # The AI signals escalation with a [HANDOFF] marker at the start of its
        # reply; the marker is stripped before saving — clients never see it.
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
            }, service["id"])
            await self.ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)},
                                    service["id"])

        if wants_handoff and not dialog.get("operator_called"):
            ai_settings = await self.db.get_setting_json("ai_settings", {}, service["id"])
            if ai_settings.get("handoff_enabled", True):
                await self._auto_handoff(dialog_id, dialog)

    async def _handle_callback(self, data: dict):
        callback_data = data.get("callback_data", "")

        if callback_data.startswith("call_op:"):
            dialog_id = callback_data.split(":")[1]
            dialog = await self.db.get_dialog(dialog_id)
            if not dialog or dialog.get("operator_called"):
                return
            # ai → full handoff; already-escalated → flag + re-notify operators
            op_name = await self.routing.on_operator_requested(dialog)
            if op_name:
                print(f"[callback] operator called → with {op_name} for dialog={dialog_id}")
            else:
                print(f"[callback] operator called → no free slot, queued dialog={dialog_id}")

        elif callback_data.startswith("rate:"):
            parts = callback_data.split(":")
            if len(parts) == 3:
                dialog_id, score = parts[1], parts[2]
                try:
                    await self.db.set_dialog_rating(dialog_id, int(score))
                    print(f"[callback] rating={score} for dialog={dialog_id}")
                    updated = await self.db.get_dialog(dialog_id)
                    if updated:
                        await self.ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)},
                                                updated["service_id"])
                        chat_id = updated.get("chat_id") or data.get("chat_id")
                        if chat_id:
                            automation = await self.db.get_setting_json(
                                "automation", {}, updated["service_id"]
                            )
                            thanks = automation.get("rating_thanks_text") or "Спасибо за оценку! 🙏"
                            await self.n8n.send_to_user(str(chat_id), thanks, service=updated)
                except ValueError:
                    pass

    async def _handle_delivery_confirmation(self, data: dict):
        message_id = data.get("message_id")
        dialog_id  = data.get("dialog_id")
        status     = data.get("status")
        error      = data.get("error")
        if not message_id or not status:
            return
        await self.db.update_message_delivery(int(message_id), status, error)
        dialog = await self.db.get_dialog(dialog_id) if dialog_id else None
        await self.ws.broadcast({
            "type":       "message_status",
            "dialog_id":  dialog_id,
            "message_id": int(message_id),
            "status":     status,
            "error":      error,
        }, dialog["service_id"] if dialog else None)

    async def _auto_handoff(self, dialog_id: str, dialog: dict):
        print(f"[auto-handoff] dialog={dialog_id}")
        # RoutingEngine guards on status='ai', assigns or queues, disables AI,
        # records the system message, broadcasts and notifies operator_called.
        await self.routing.handoff_from_ai(dialog_id)
