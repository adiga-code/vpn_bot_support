"""Провайдеры состояния VPN-серверов.

Реализуют контракт app.health.HealthProvider и регистрируются внизу файла.
Какой из них работает у конкретного ВПН-а — задаётся в пер-сервисной настройке
`monitoring.servers.provider`.

    mock  — случайные данные (по умолчанию, пока нет реального источника)
    tcp   — доступность через TCP-соединение
    http  — health-эндпоинт, отдающий JSON с load/uptime
"""
import asyncio
import hashlib
import random
import time
from dataclasses import dataclass

import aiohttp

from app.health import SERVERS, ComponentStatus, HealthProvider, register_provider
from app.redact import redact


@dataclass
class ServerInfo:
    name: str
    host: str                   # IP or hostname
    location: str = ""
    port: int = 443             # port for TCP / HTTP check
    load_warn_pct: float = 80   # load above this threshold → status "high"


def parse_servers(raw: list[dict]) -> list[ServerInfo]:
    return [
        ServerInfo(
            name=s["name"],
            host=s.get("host", ""),
            location=s.get("location", ""),
            port=int(s.get("port", 443)),
            load_warn_pct=float(s.get("load_warn_pct", 80)),
        )
        for s in (raw or [])
    ]


class _ServerProvider(HealthProvider):
    """Общая часть: список серверов из конфига и параллельный опрос."""

    kind = SERVERS

    def __init__(self, service: dict, config: dict = None):
        super().__init__(service, config)
        self.servers = parse_servers(self.config.get("servers"))

    async def check(self) -> list[ComponentStatus]:
        if not self.servers:
            return [self.make(
                "no-servers", "Серверы не заданы", "unknown",
                message="В настройках мониторинга сервиса пустой список servers",
            )]
        results = await asyncio.gather(
            *(self.check_one(s) for s in self.servers), return_exceptions=True
        )
        return [
            r if isinstance(r, ComponentStatus)
            else self.make(_sid(s), s.name, "unknown", location=s.location,
                           message=str(r)[:200])
            for s, r in zip(self.servers, results)
        ]

    async def check_one(self, server: ServerInfo) -> ComponentStatus:
        raise NotImplementedError


def _sid(server: ServerInfo) -> str:
    return f"srv-{server.name}"


# ── Реальные источники ────────────────────────────────────────────────────────

class TcpServerProvider(_ServerProvider):
    """Доступность по TCP: работает для любого порта, но без нагрузки и uptime."""

    source = "tcp"

    def __init__(self, service: dict, config: dict = None):
        super().__init__(service, config)
        self.timeout = float(self.config.get("timeout", 5.0))

    async def check_one(self, server: ServerInfo) -> ComponentStatus:
        start = time.monotonic()
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(server.host, server.port),
                timeout=self.timeout,
            )
            writer.close()
            await writer.wait_closed()
            ping_ms = round((time.monotonic() - start) * 1000, 1)
            return self.make(_sid(server), server.name, "ok",
                             location=server.location, metrics={"ping": ping_ms})
        except (asyncio.TimeoutError, OSError) as e:
            return self.make(_sid(server), server.name, "down",
                             location=server.location, message=redact(e)[:200] or "нет соединения")


class HttpServerProvider(_ServerProvider):
    """Health-эндпоинт сервера: JSON вида {"load": 42.5, "uptime": 99.9}."""

    source = "http"

    def __init__(self, service: dict, config: dict = None):
        super().__init__(service, config)
        self.timeout = aiohttp.ClientTimeout(total=float(self.config.get("timeout", 10.0)))
        self.health_path = self.config.get("health_path", "/health")

    async def check_one(self, server: ServerInfo) -> ComponentStatus:
        url = f"https://{server.host}:{server.port}{self.health_path}"
        start = time.monotonic()
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url, ssl=False) as resp:
                    ping_ms = round((time.monotonic() - start) * 1000, 1)
                    if resp.status >= 400:
                        return self.make(_sid(server), server.name, "down",
                                         location=server.location,
                                         message=f"HTTP {resp.status}")
                    try:
                        body = await resp.json(content_type=None)
                    except Exception:
                        body = {}
                    load = body.get("load")
                    uptime = body.get("uptime")
                    high = load is not None and load > server.load_warn_pct
                    return self.make(
                        _sid(server), server.name, "high" if high else "ok",
                        location=server.location,
                        metrics={"ping": ping_ms, "load": load, "uptime": uptime},
                        message=f"нагрузка выше {server.load_warn_pct}%" if high else "",
                    )
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            return self.make(_sid(server), server.name, "down",
                             location=server.location, message=redact(e)[:200] or "недоступен")


# ── Мок ───────────────────────────────────────────────────────────────────────

# ВНИМАНИЕ: данные ниже выдуманы. Это заглушка на время, пока не подключён
# реальный источник — панель VPN, Prometheus, свой API. Набор серверов
# детерминированно выводится из слага сервиса, чтобы у разных ВПН-ов были
# разные (но стабильные между перезапусками) города, а метрики слегка плавают,
# чтобы экран выглядел живым.

_MOCK_LOCATIONS = [
    ("Frankfurt", "DE"), ("Amsterdam", "NL"), ("Warsaw", "PL"), ("Stockholm", "SE"),
    ("Paris", "FR"), ("London", "UK"), ("Vienna", "AT"), ("Helsinki", "FI"),
    ("Zurich", "CH"), ("Madrid", "ES"),
]


class MockServerProvider(_ServerProvider):
    """МОК: выдуманные серверы со случайными метриками."""

    source = "mock"
    is_mock = True

    def __init__(self, service: dict, config: dict = None):
        super().__init__(service, config)
        if not self.servers:
            self.servers = self._mock_servers()
        self._rnd = random.Random(self._seed())

    def _seed(self) -> int:
        slug = self.service.get("slug", "")
        return int(hashlib.md5(slug.encode()).hexdigest()[:8], 16)

    def _mock_servers(self) -> list[ServerInfo]:
        rnd = random.Random(self._seed())
        count = rnd.randint(3, 6)
        picked = rnd.sample(_MOCK_LOCATIONS, count)
        return [
            ServerInfo(name=f"{city}-{i + 1:02d}", host="mock", location=code)
            for i, (city, code) in enumerate(picked)
        ]

    async def check(self) -> list[ComponentStatus]:
        # Один «проблемный» сервер на сервис — чтобы на экране были видны все
        # состояния, а не сплошной зелёный.
        bad_idx = self._seed() % max(1, len(self.servers))
        out = []
        for i, s in enumerate(self.servers):
            if i == bad_idx and self._rnd.random() < 0.5:
                status, load = "high", round(self._rnd.uniform(82, 97), 1)
                message = "МОК: имитация высокой нагрузки"
            else:
                status, load = "ok", round(self._rnd.uniform(8, 65), 1)
                message = ""
            out.append(self.make(
                _sid(s), s.name, status, location=s.location, message=message,
                metrics={
                    "ping": round(self._rnd.uniform(5, 80), 1),
                    "load": load,
                    "uptime": round(self._rnd.uniform(98.5, 100), 2),
                },
            ))
        return out


register_provider("mock", MockServerProvider)
register_provider("tcp", TcpServerProvider)
register_provider("http", HttpServerProvider)
