"""Провайдеры состояния ботов ВПН-сервиса.

Боевой источник — ваша infra-API (`app/infra.py`, провайдер `infra_bots`):
панель к ней подключается и показывает то, что она отдаёт. Здесь остаётся
только мок на время, пока API не поднята.
"""
import hashlib
import random
from datetime import datetime, timedelta, timezone

from app.health import BOTS, ComponentStatus, HealthProvider, register_provider

# ВНИМАНИЕ: данные ниже выдуманы. Заглушка на время, пока не подключена
# infra-API. Состав ботов детерминирован по слагу сервиса (у каждого ВПН-а свои
# имена), метрики слегка плавают между опросами.


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
                message = "МОК: бот не отвечает (имитация)"
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
