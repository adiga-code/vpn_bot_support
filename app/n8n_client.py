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
    """Publishes outbound events to n8n via per-service Redis channels.

    Each VPN brand runs its own copy of the n8n workflows, so every channel
    carries a `:{slug}` suffix — otherwise each copy would receive the other
    brands' traffic. While PUBLISH_LEGACY_CHANNELS is on, the default service
    also publishes to the old unsuffixed names so workflows can be migrated
    one at a time.
    """

    def __init__(self, settings: Settings, redis: aioredis.Redis, db: "DatabaseManager | None" = None):
        self.settings = settings
        self.redis = redis
        self.db = db
        self._default_slug: str | None = None

    # ── Channel naming ────────────────────────────────────────────────────────

    async def _legacy_slug(self) -> str | None:
        if not self.settings.PUBLISH_LEGACY_CHANNELS:
            return None
        if self._default_slug is None and self.db:
            service = await self.db.get_default_service()
            self._default_slug = service["slug"] if service else ""
        return self._default_slug or None

    async def _publish(self, event: str, slug: str, payload: dict) -> None:
        body = json.dumps({**payload, "service": slug}, ensure_ascii=False)
        await self.redis.publish(f"vpn_bot:{event}:{slug}", body)
        if slug == await self._legacy_slug():
            await self.redis.publish(f"vpn_bot:{event}", body)

    # ── Schedule helpers ──────────────────────────────────────────────────────

    async def _is_within_schedule(self, service_id: int) -> bool:
        if not self.db:
            return True
        schedule = await self.db.get_service_setting_json(
            service_id, "schedule", _SCHEDULE_DEFAULTS
        )
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

    async def _flush_pending(self, slug: str) -> None:
        """Publish all queued off-hours notifications for this service."""
        key = f"vpn_bot:pending_notifications:{slug}"
        while True:
            item = await self.redis.lpop(key)
            if not item:
                break
            try:
                data = json.loads(item)
                event_type = data.pop("type")
                data.pop("service", None)
                await self.notify_event(event_type, slug, data)
                print(f"[schedule] flushed: {event_type} ({slug})")
            except Exception as e:
                print(f"[schedule] flush error: {e}")

    # ── Outbound messages ─────────────────────────────────────────────────────

    async def send_manager_message(
        self,
        external_id: str,
        chat_id: str,
        slug: str,
        message: str,
        file_id: str = None,
        file_type: str = None,
        file_url: str = None,
    ) -> bool:
        try:
            payload = {
                "type": "manager_message",
                "dialog_id": external_id,
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
            await self._publish("messages", slug, payload)
            return True
        except Exception as e:
            print(f"Error sending manager message: {e}")
            return False

    async def notify_dialog_closed(self, external_id: str, chat_id: str, slug: str, operator_name: str) -> None:
        try:
            await self._publish("dialog_closed", slug, {
                "type": "dialog_closed",
                "dialog_id": external_id,
                "chat_id": chat_id,
                "operator_name": operator_name,
            })
        except Exception as e:
            print(f"notify_dialog_closed error (non-critical): {e}")

    async def notify_ai_toggled(self, external_id: str, chat_id: str, slug: str, ai_enabled: bool) -> None:
        try:
            await self._publish("ai_toggled", slug, {
                "type": "ai_toggled",
                "dialog_id": external_id,
                "chat_id": chat_id,
                "ai_enabled": ai_enabled,
            })
        except Exception as e:
            print(f"notify_ai_toggled error (non-critical): {e}")

    async def notify_event(self, event_type: str, slug: str, payload: dict) -> None:
        """Direct publish — bypasses schedule. Use schedule_notify for operator alerts."""
        try:
            await self._publish("notifications", slug, {"type": event_type, **payload})
        except Exception as e:
            print(f"notify_event error (non-critical): {e}")

    async def schedule_notify(self, event_type: str, service: dict, payload: dict) -> None:
        """Schedule-aware notification: queues during off-hours, flushes at day start.

        Working hours are per service — brands do not share a support shift.
        """
        slug = service["slug"]
        try:
            if not await self._is_within_schedule(service["id"]):
                await self.redis.rpush(
                    f"vpn_bot:pending_notifications:{slug}",
                    json.dumps({"type": event_type, **payload}, ensure_ascii=False),
                )
                print(f"[schedule] queued {event_type} for {slug} (outside working hours)")
                return
            await self._flush_pending(slug)
            await self.notify_event(event_type, slug, payload)
        except Exception as e:
            print(f"schedule_notify error (non-critical): {e}")

    async def send_billing_action(self, external_id: str, chat_id: str, slug: str, action: str) -> bool:
        try:
            await self._publish("billing", slug, {
                "type": "billing_action",
                "dialog_id": external_id,
                "chat_id": chat_id,
                "action": action,
            })
            return True
        except Exception as e:
            print(f"Billing action error: {e}")
            return False

    # ── Shared config keys ────────────────────────────────────────────────────

    async def push_ai_settings(self, slug: str, data: dict) -> None:
        """Mirror a service's AI settings into the key its n8n AI Agent reads."""
        body = json.dumps(data, ensure_ascii=False)
        await self.redis.set(f"vpn_bot:ai_settings:{slug}", body)
        if slug == await self._legacy_slug():
            await self.redis.set("vpn_bot:ai_settings", body)

    async def push_schedule(self, slug: str, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False)
        await self.redis.set(f"vpn_bot:schedule:{slug}", body)
        if slug == await self._legacy_slug():
            await self.redis.set("vpn_bot:schedule", body)

    def invalidate_default_slug(self) -> None:
        """Call after the default service changes so legacy mirroring follows it."""
        self._default_slug = None
