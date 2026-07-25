"""Провайдеры состояния Telegram-ботов ВПН-сервиса.

Тот же контракт, что и у серверов (app.health.HealthProvider). Выбирается в
пер-сервисной настройке `monitoring.bots.provider`:

    mock_bot  — выдуманные данные (по умолчанию)
    telegram  — реальная проверка через Bot API (нужен токен, см. ниже)
"""
import hashlib
import random
from datetime import datetime, timedelta, timezone

import aiohttp

from app.health import BOTS, ComponentStatus, HealthProvider, register_provider

_API = "https://api.telegram.org"


class TelegramBotProvider(HealthProvider):
    """Проверка через Telegram Bot API: getMe + getWebhookInfo.

    Токены ботов живут в n8n и в панели не хранятся, поэтому провайдер
    работает, только если токен сознательно продублировали в настройки
    мониторинга сервиса:

        {"bots": {"provider": "telegram", "config": {"bots": [
            {"name": "Клиентский бот", "token": "123:ABC"}
        ]}}}

    Настоящий признак «бот встал» — не getMe (он отвечает всегда, пока токен
    жив), а getWebhookInfo: растущий pending_update_count и last_error_message.
    """

    kind = BOTS
    source = "telegram"

    async def check(self) -> list[ComponentStatus]:
        bots = self.config.get("bots") or []
        if not bots:
            return [self.make(
                "bots-no-token", "Токен не задан", "unknown",
                message="Токены ботов хранятся в n8n. Чтобы проверять их здесь, "
                        "укажите token в настройках мониторинга сервиса",
            )]
        return [await self._check_one(b, i) for i, b in enumerate(bots)]

    async def _check_one(self, bot: dict, idx: int) -> ComponentStatus:
        name = bot.get("name") or f"Бот {idx + 1}"
        token = bot.get("token") or ""
        cid = f"bot-{bot.get('id') or idx}"
        if not token:
            return self.make(cid, name, "unknown", message="не указан token")
        try:
            timeout = aiohttp.ClientTimeout(total=float(self.config.get("timeout", 10)))
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.get(f"{_API}/bot{token}/getMe") as r:
                    me = await r.json(content_type=None)
                if not me.get("ok"):
                    return self.make(cid, name, "down",
                                     message=me.get("description", "getMe вернул ошибку")[:200])
                username = me["result"].get("username", "")
                async with s.get(f"{_API}/bot{token}/getWebhookInfo") as r:
                    hook = (await r.json(content_type=None)).get("result", {})
        except Exception as e:
            return self.make(cid, name, "down", message=str(e)[:200] or "нет связи с Bot API")

        pending = int(hook.get("pending_update_count") or 0)
        last_error = hook.get("last_error_message") or ""
        mode = "webhook" if hook.get("url") else "polling"
        warn_at = int(self.config.get("pending_warn", 50))

        status = "ok"
        message = ""
        if last_error:
            status, message = "down", last_error[:200]
        elif pending > warn_at:
            status, message = "high", f"накопилось {pending} необработанных апдейтов"

        return self.make(cid, name if not username else f"@{username}", status,
                         message=message,
                         metrics={"mode": mode, "pendingUpdates": pending,
                                  "webhook": hook.get("url") or None})


# ── Мок ───────────────────────────────────────────────────────────────────────

# ВНИМАНИЕ: данные ниже выдуманы. Заглушка на время, пока не подключён реальный
# источник. Состав ботов детерминирован по слагу сервиса (у каждого ВПН-а свои
# имена), а метрики слегка плавают между опросами.

class MockBotProvider(HealthProvider):
    """МОК: выдуманные боты сервиса со случайными метриками."""

    kind = BOTS
    source = "mock"
    is_mock = True

    def __init__(self, service: dict, config: dict = None):
        super().__init__(service, config)
        slug = self.service.get("slug", "vpn")
        self._seed = int(hashlib.md5(slug.encode()).hexdigest()[:8], 16)
        self._rnd = random.Random(self._seed)

    async def check(self) -> list[ComponentStatus]:
        slug = self.service.get("slug", "vpn")
        now = datetime.now(timezone.utc)
        bots = [
            {"id": "client", "name": f"@{slug}_bot", "role": "Клиентский бот",
             "mode": "webhook"},
            {"id": "notify", "name": f"@{slug}_ops_bot", "role": "Бот уведомлений",
             "mode": "polling"},
        ]
        out = []
        # Один сервис из нескольких показываем «прилёгшим», чтобы на экране были
        # видны разные состояния.
        broken = self._seed % 3 == 0
        for i, b in enumerate(bots):
            pending = self._rnd.randint(0, 4)
            status, message = "ok", ""
            if broken and i == 1:
                status = "down"
                message = "МОК: Bot API не отвечает (имитация)"
            elif pending > 3:
                status = "high"
                message = "МОК: очередь апдейтов растёт"
            lag = self._rnd.randint(1, 90)
            out.append(self.make(
                b["id"], b["name"], status, message=message,
                metrics={
                    "role": b["role"],
                    "mode": b["mode"],
                    "pendingUpdates": pending,
                    "lastUpdate": (now - timedelta(seconds=lag)).isoformat(),
                },
            ))
        return out


register_provider("mock_bot", MockBotProvider)
register_provider("telegram", TelegramBotProvider)
