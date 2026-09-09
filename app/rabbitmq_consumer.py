import asyncio
import json

import aio_pika
import aio_pika.abc

from app.ai_client import ChatClient
from app.classifier import classify_message
from app.database import DatabaseManager
from app.dialogs import parse_ai_enabled, resolve_service, user_info_from
from app.media import internalize
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
        fallback=None,
        storage=None,
        settings=None,
    ):
        self._rmq = rmq
        self.db = db
        self.ws = ws
        self.n8n = n8n
        self.routing = routing
        self.chat_client = chat_client
        # FallbackSenderService — резервный канал доставки; None означает, что
        # панель собрана без него.
        self.fallback = fallback
        # Хранилище и настройки нужны, чтобы забрать вложение по чужой ссылке
        # к себе: в ссылке от n8n может стоять токен бота, а её видит браузер
        # оператора. Без них внешние ссылки просто отбрасываются.
        self.storage = storage
        self.settings = settings

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

    async def _internal_url(self, url: str) -> str:
        """Ссылка на своё хранилище вместо чужой. Панель собрана без хранилища
        — внешняя ссылка отбрасывается, а не сохраняется как есть."""
        if not url:
            return url
        if not self.storage or not self.settings:
            return ""
        return await internalize(url, self.storage, self.settings)

    async def _dialog_for(self, data: dict, service: dict | None,
                          prefer_open: bool = True) -> dict | None:
        """Тикет, которому принадлежит событие.

        Личность диалога — пара (сервис, chat_id); `dialog_id` в событии лишь
        подсказка. Если по нему тикет не нашёлся (n8n прислал устаревший номер,
        событие пришло из старого воркфлоу), берём открытый тикет клиента, а не
        заводим второй.

        `prefer_open=False` — для событий, которые относятся именно к тому
        тикету, номер которого назван: оценка приходит на уже закрытый тикет,
        и переносить её на следующее обращение клиента нельзя.
        """
        dialog_id = str(data.get("dialog_id") or "").strip()
        known = await self.db.get_dialog(dialog_id) if dialog_id else None
        if known and (not prefer_open or known["status"] != "closed"):
            return known
        # Номера закрытого тикета мало: пока событие шло, клиент мог начать
        # новое обращение — оно и есть текущее.
        chat_id = str(data.get("chat_id") or "").strip()
        open_dialog = await self.db.get_active_dialog_by_chat_id(
            service["id"], chat_id) if service and chat_id else None
        return open_dialog or known

    async def _handle_user_message(self, data: dict):
        service = await resolve_service(self.db, data)
        if not service:
            return
        chat_id = str(data["chat_id"])
        text = data.get("message", "")
        file_id = data.get("file_id")
        file_type = data.get("file_type", "text")
        file_url = data.get("file_url")
        # n8n sometimes puts the uploaded URL into file_id instead of file_url
        if not file_url and file_id and str(file_id).startswith("http"):
            file_url, file_id = file_id, None
        # Ссылка наружу до базы не доезжает: в ней может стоять токен бота, а
        # её подставит в <img src> браузер оператора. Забираем файл к себе.
        file_url = await self._internal_url(file_url)
        ai_enabled = parse_ai_enabled(data.get("ai_enabled"))
        operator_called = bool(data.get("operator_called", False))

        # dialog_id из события не участвует: тикет ищется по (сервис, chat_id),
        # поэтому чужой или устаревший номер не может завести второй тикет.
        dialog_row = await self.db.resolve_open_dialog(
            service, chat_id, ai_enabled, user_info_from(data), bump_unread=True
        )
        dialog_id = dialog_row["dialog_id"]

        msg_row = await self.db.save_message(
            dialog_id,
            "user",
            text if file_type == "text" else None,
            file_id=file_id if file_type != "text" else None,
            file_type=file_type if file_type != "text" else None,
            file_url=file_url,
        )
        await self.db.update_last_message(dialog_id, text or f"[{file_type}]")
        # «Новый тикет» для панели — это первое сообщение клиента в нём.
        # Саму строку могла завести и ручка resolve, которую n8n дёргает
        # раньше; уведомлять операторов надо всё равно один раз и с текстом.
        is_new = await self.db.get_user_message_count(dialog_id) == 1

        if text and file_type == "text":
            asyncio.create_task(self._classify_later(msg_row["id"], text, service["id"]))

        if operator_called:
            await self.db.update_operator_called(dialog_id, True)

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
        service = await resolve_service(self.db, data)
        if not service:
            return
        text = data.get("message", "")

        dialog = await self._dialog_for(data, service)
        if not dialog:
            print(f"[consumer] ответ ИИ не к чему привязать: "
                  f"dialog_id={data.get('dialog_id')!r} chat_id={data.get('chat_id')!r}")
            return
        dialog_id = dialog["dialog_id"]

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
        service = await resolve_service(self.db, data)
        if not service:
            return

        if callback_data.startswith("call_op:"):
            # Кнопка помнит номер тикета на момент отправки; открытый тикет
            # клиента — источник правды, если тот номер уже закрыт.
            dialog = await self._dialog_for(
                {**data, "dialog_id": callback_data.split(":", 1)[1]}, service
            )
            if not dialog or dialog.get("operator_called"):
                return
            dialog_id = dialog["dialog_id"]
            # ai → full handoff; already-escalated → flag + re-notify operators
            op_name = await self.routing.on_operator_requested(dialog)
            if op_name:
                print(f"[callback] operator called → with {op_name} for dialog={dialog_id}")
            else:
                print(f"[callback] operator called → no free slot, queued dialog={dialog_id}")

        elif callback_data.startswith("rate:"):
            parts = callback_data.split(":")
            if len(parts) == 3:
                score = parts[2]
                # оценка принадлежит именно оценённому (уже закрытому) тикету
                dialog = await self._dialog_for(
                    {**data, "dialog_id": parts[1]}, service, prefer_open=False)
                if not dialog:
                    return
                dialog_id = dialog["dialog_id"]
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
        status     = data.get("status")
        error      = data.get("error")
        if not message_id or not status:
            return
        message_id = int(message_id)
        # Подтверждение относится к конкретному отправленному сообщению —
        # берём тикет по его номеру, даже если он уже закрыт.
        dialog = await self._dialog_for(data, None, prefer_open=False)

        if status == "failed" and dialog:
            status, error = await self.try_fallback(dialog, message_id, error)

        await self.db.update_message_delivery(message_id, status, error)
        await self.ws.broadcast({
            "type":       "message_status",
            "dialog_id":  dialog["dialog_id"] if dialog else data.get("dialog_id"),
            "message_id": message_id,
            "status":     status,
            "error":      error,
        }, dialog["service_id"] if dialog else None)

    async def try_fallback(self, dialog: dict, message_id: int,
                           original_error: str) -> tuple[str, str]:
        """Ответ оператора не дошёл — пробуем ещё раз, но по MTProto, от того же
        аккаунта поддержки (см. app/fallback_sender.py). Возвращает статус и
        текст ошибки для строки сообщения.

        Пробуем на ЛЮБОЙ неуспешной доставке, а не только на
        BUSINESS_PEER_USAGE_MISSING: «бот заблокирован пользователем» и обрыв
        очереди резервный канал лечит ровно так же.
        """
        original_error = original_error or "Ошибка отправки"
        if not self.fallback:
            return "failed", original_error
        row = await self.db.get_message(message_id)
        if not row or row.get("kind") != "operator":
            return "failed", original_error

        ok, detail = await self.fallback.send(
            dialog["service_id"], dialog["chat_id"],
            row.get("text") or "", row.get("file_url"),
        )
        if not detail:                      # резервный канал не настроен
            return "failed", original_error

        note = (f"Сообщение не ушло в business-чат ({original_error}) — "
                + (f"{detail}" if ok else f"резервная отправка тоже не удалась: {detail}"))
        sys_row = await self.db.save_message(dialog["dialog_id"], "system", note)
        await self.ws.broadcast({"type": "new_message", "dialog_id": dialog["dialog_id"],
                                 "message": _fmt_message(sys_row)}, dialog["service_id"])
        if ok:
            # Исходную причину не теряем: оператор должен понимать, почему
            # сообщение ушло другим путём, и что business-подключение сломано.
            return "delivered_fallback", original_error
        return "failed", f"{original_error} · резерв: {detail}"

    async def _auto_handoff(self, dialog_id: str, dialog: dict):
        print(f"[auto-handoff] dialog={dialog_id}")
        # RoutingEngine guards on status='ai', assigns or queues, disables AI,
        # records the system message, broadcasts and notifies operator_called.
        await self.routing.handoff_from_ai(dialog_id)
