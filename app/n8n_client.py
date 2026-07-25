import asyncio
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import aiohttp
import aio_pika
import aio_pika.abc
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

QUEUE_OUTGOING = "vpn_bot.outgoing"
QUEUE_PENDING  = "vpn_bot.pending_notifications"


def service_ctx(source: dict | None) -> tuple[str, str]:
    """(slug, webhook_url) сервиса — из строки диалога (service_slug) либо из
    строки самого сервиса (slug). Пустой slug означает «сервис неизвестен»:
    такое сообщение уйдёт без маршрутизации, на дефолтный вебхук."""
    if not source:
        return "", ""
    slug = source.get("service_slug") or source.get("slug") or ""
    return slug, source.get("n8n_webhook_url") or ""


class N8NClient:
    """All outbound events go to RabbitMQ queue vpn_bot.outgoing.
    n8n reads with a RabbitMQ Trigger node and routes by the `type` field.

    Каждое сообщение несёт поле `service` — слаг ВПН-а. По нему роутер n8n
    выбирает нужного Telegram-бота (токены живут в n8n, не здесь). Если у
    сервиса задан собственный n8n_webhook_url, событие уходит на него —
    так поддерживается вариант с отдельным инстансом n8n на каждый ВПН.

    Message types:
      manager_message  — operator reply to user (text/file)
      operator_notify  — notification to the operator group (event field varies)
      send_to_user     — proactive message to user, optional inline keyboard
      billing_action   — billing command for user
    """

    def __init__(
        self,
        settings: Settings,
        rmq: aio_pika.abc.AbstractRobustConnection,
        redis: aioredis.Redis,
        db: "DatabaseManager | None" = None,
    ):
        self.settings = settings
        self._rmq = rmq
        self.redis = redis  # kept for KV ops: vpn_bot:ai_settings, vpn_bot:schedule
        self.db = db
        self._channel: aio_pika.abc.AbstractChannel | None = None

    async def _get_channel(self) -> aio_pika.abc.AbstractChannel:
        if self._channel is None or self._channel.is_closed:
            self._channel = await self._rmq.channel()
            await self._channel.declare_queue(QUEUE_OUTGOING, durable=True)
            await self._channel.declare_queue(QUEUE_PENDING,  durable=True)
        return self._channel

    # ── Core push ─────────────────────────────────────────────────────────────

    async def _push(self, payload: dict, service: dict = None) -> bool:
        """Deliver an outgoing event to n8n.

        Primary channel is the n8n Webhook — свой у сервиса, если задан, иначе
        общий N8N_WEBHOOK_URL — plain HTTP trigger, immune to the flaky
        RabbitMQ Trigger node. When the webhook is not configured or fails
        after retries, falls back to RabbitMQ (очередь общая, разбор по полю
        `service`).
        """
        slug, service_url = service_ctx(service)
        if slug:
            payload = {**payload, "service": slug}
        url = service_url or self.settings.N8N_WEBHOOK_URL
        if url:
            if await self._push_webhook(payload, url):
                return True
            print("[n8n] webhook delivery failed — falling back to RabbitMQ")
        return await self._push_rmq(payload)

    async def _push_webhook(self, payload: dict, url: str) -> bool:
        headers = {}
        if self.settings.N8N_API_KEY:
            headers["X-API-Key"] = self.settings.N8N_API_KEY
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        if resp.status < 300:
                            return True
                        print(f"[n8n] webhook HTTP {resp.status} (attempt {attempt + 1}/3)")
            except Exception as e:
                print(f"[n8n] webhook error: {e} (attempt {attempt + 1}/3)")
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
        return False

    async def _push_rmq(self, payload: dict) -> bool:
        try:
            ch = await self._get_channel()
            await ch.default_exchange.publish(
                aio_pika.Message(
                    body=json.dumps(payload, ensure_ascii=False).encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=QUEUE_OUTGOING,
            )
            return True
        except Exception as e:
            print(f"[n8n] push error: {e}")
            return False

    # ── Schedule helpers ──────────────────────────────────────────────────────

    async def _is_within_schedule(self, service_id: int = None) -> bool:
        if not self.db:
            return True
        schedule = await self.db.get_setting_json("schedule", _SCHEDULE_DEFAULTS, service_id)
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
        """Отложенные уведомления помнят свой сервис (_service в теле) — иначе
        при разборе очереди события ушли бы не тому боту."""
        try:
            ch = await self._get_channel()
            queue = await ch.declare_queue(QUEUE_PENDING, durable=True)
            while True:
                msg = await queue.get(no_ack=False, fail=False)
                if msg is None:
                    break
                try:
                    data = json.loads(msg.body)
                    event_type = data.pop("type")
                    service = data.pop("_service", None)
                    await msg.ack()
                    await self.notify_event(event_type, data, service)
                    print(f"[schedule] flushed: {event_type}")
                except Exception as e:
                    await msg.nack(requeue=True)
                    print(f"[schedule] flush error: {e}")
        except Exception as e:
            print(f"[schedule] _flush_pending error: {e}")

    # ── Operator notifications ─────────────────────────────────────────────────

    async def notify_event(self, event_type: str, payload: dict, service: dict = None) -> None:
        """Direct push — bypasses schedule. Use schedule_notify for operator alerts."""
        await self._push({"type": "operator_notify", "event": event_type, **payload}, service)

    async def schedule_notify(self, event_type: str, payload: dict, service: dict = None) -> None:
        """Schedule-aware: queues off-hours, flushes at start of working day.
        Расписание своё у каждого сервиса."""
        try:
            slug, url = service_ctx(service)
            service_id = (service or {}).get("service_id") or (service or {}).get("id")
            if not await self._is_within_schedule(service_id):
                ch = await self._get_channel()
                body = {"type": event_type, **payload}
                if slug:
                    body["_service"] = {"slug": slug, "n8n_webhook_url": url}
                await ch.default_exchange.publish(
                    aio_pika.Message(
                        body=json.dumps(body, ensure_ascii=False).encode(),
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    ),
                    routing_key=QUEUE_PENDING,
                )
                print(f"[schedule] queued {event_type} (outside working hours)")
                return
            await self._flush_pending()
            await self.notify_event(event_type, payload, service)
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
        message_id: int = None,
        service: dict = None,
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
        if message_id is not None:
            payload["message_id"] = message_id
        return await self._push(payload, service)

    async def notify_dialog_closed(
        self, dialog_id: str, chat_id: str, operator_name: str, service: dict = None,
    ) -> None:
        await self._push({
            "type": "operator_notify",
            "event": "dialog_closed",
            "dialog_id": dialog_id,
            "chat_id": chat_id,
            "operator_name": operator_name,
        }, service)

    async def notify_ai_toggled(
        self, dialog_id: str, chat_id: str, ai_enabled: bool, service: dict = None,
    ) -> None:
        await self._push({
            "type": "operator_notify",
            "event": "ai_toggled",
            "dialog_id": dialog_id,
            "chat_id": chat_id,
            "ai_enabled": ai_enabled,
        }, service)

    # ── Direct user messaging ─────────────────────────────────────────────────

    async def send_to_user(
        self, chat_id: str, text: str, keyboard: list = None, service: dict = None,
    ) -> bool:
        payload = {"type": "send_to_user", "chat_id": chat_id, "text": text}
        if keyboard:
            payload["keyboard"] = keyboard
        return await self._push(payload, service)

    async def send_operator_button(self, chat_id: str, dialog_id: str, service: dict = None) -> bool:
        keyboard = [[{"text": "👨‍💼 Позвать оператора", "callback_data": f"call_op:{dialog_id}"}]]
        return await self.send_to_user(chat_id, "Нужна помощь живого оператора? 👇", keyboard, service)

    async def send_rating_request(
        self, chat_id: str, dialog_id: str,
        text: str = "Оцените качество поддержки:", service: dict = None,
    ) -> bool:
        stars = ["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"]
        keyboard = [
            [{"text": s, "callback_data": f"rate:{dialog_id}:{i + 1}"} for i, s in enumerate(stars[:3])],
            [{"text": s, "callback_data": f"rate:{dialog_id}:{i + 4}"} for i, s in enumerate(stars[3:])],
        ]
        return await self.send_to_user(chat_id, text, keyboard, service)

    # ── Billing ───────────────────────────────────────────────────────────────

    async def send_billing_action(
        self, dialog_id: str, chat_id: str, action: str, service: dict = None,
    ) -> bool:
        return await self._push({
            "type": "billing_action",
            "dialog_id": dialog_id,
            "chat_id": chat_id,
            "action": action,
        }, service)
