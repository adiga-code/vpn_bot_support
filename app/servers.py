"""
VPN server monitoring — OOP, легко подключить свою реализацию.

Чтобы добавить свой провайдер:
    class MyMonitor(ServerMonitor):
        async def check_one(self, server: ServerInfo) -> ServerResult: ...

Зарегистрировать в make_server_monitor() или передать напрямую в main.py.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import aiohttp

StatusType = Literal["ok", "high", "down", "unknown"]


@dataclass
class ServerInfo:
    """Конфигурация одного сервера для мониторинга."""
    name: str
    host: str                   # IP или hostname
    location: str = ""
    port: int = 443             # порт для TCP / HTTP проверки
    load_warn_pct: float = 80   # выше этого → статус "high"


@dataclass
class ServerResult:
    """Результат одной проверки сервера (то, что видит frontend)."""
    name: str
    status: StatusType
    location: str = ""
    ping: float | None = None   # мс
    load: float | None = None   # %
    uptime: float | None = None  # %


class ServerMonitor(ABC):
    """Базовый класс. Реализуй check_one() — остальное бесплатно."""

    def __init__(self, servers: list[ServerInfo], interval: int = 300):
        self.servers = servers
        self.interval = interval          # секунды между проверками
        self._results: list[ServerResult] = []
        self._last_updated: str | None = None

    # ── Публичный интерфейс ───────────────────────────────────────────────────

    def get_snapshot(self) -> dict:
        """Возвращает данные для /api/servers в формате, который ждёт frontend."""
        return {
            "servers": [self._result_to_dict(r) for r in self._results],
            "last_updated": self._last_updated,
        }

    async def run_forever(self):
        """Фоновый цикл. Запускать через asyncio.gather() в main.py."""
        print(f"✅ Server monitor started ({len(self.servers)} servers, interval={self.interval}s)")
        while True:
            await self._run_check()
            await asyncio.sleep(self.interval)

    # ── Для переопределения ───────────────────────────────────────────────────

    @abstractmethod
    async def check_one(self, server: ServerInfo) -> ServerResult:
        """Проверить один сервер. Реализуй в своём классе."""

    # ── Внутренние ───────────────────────────────────────────────────────────

    async def _run_check(self):
        tasks = [self.check_one(s) for s in self.servers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        self._results = [
            r if isinstance(r, ServerResult)
            else ServerResult(name=s.name, status="unknown", location=s.location)
            for s, r in zip(self.servers, results)
        ]
        self._last_updated = datetime.now().strftime("%d.%m.%Y %H:%M")

    @staticmethod
    def _result_to_dict(r: ServerResult) -> dict:
        return {
            "name": r.name,
            "status": r.status,
            "location": r.location,
            "ping": r.ping,
            "load": r.load,
            "uptime": r.uptime,
        }


# ── Реализации ────────────────────────────────────────────────────────────────

class TcpServerMonitor(ServerMonitor):
    """
    Проверяет сервер через TCP-подключение.

    Плюсы:  работает для любого TCP-порта (VPN, SSH, HTTPS).
    Минусы: не знает нагрузку и uptime — только доступность и пинг.

    Для VPN-серверов обычно проверяют порт 443 (HTTPS) или 22 (SSH).
    Задай port в ServerInfo под свой протокол.
    """

    def __init__(self, servers: list[ServerInfo], interval: int = 300, timeout: float = 5.0):
        super().__init__(servers, interval)
        self.timeout = timeout

    async def check_one(self, server: ServerInfo) -> ServerResult:
        start = time.monotonic()
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(server.host, server.port),
                timeout=self.timeout,
            )
            writer.close()
            await writer.wait_closed()
            ping_ms = round((time.monotonic() - start) * 1000, 1)
            return ServerResult(
                name=server.name,
                location=server.location,
                status="ok",
                ping=ping_ms,
            )
        except (asyncio.TimeoutError, OSError):
            return ServerResult(name=server.name, location=server.location, status="down")


class HttpServerMonitor(ServerMonitor):
    """
    Проверяет сервер через HTTP GET запрос к health-эндпоинту.

    Ожидаемый ответ от твоего сервера (JSON):
        { "load": 42.5, "uptime": 99.9 }   — поля опциональны

    Если сервер не отвечает или статус != 2xx → "down".
    Если load > server.load_warn_pct → "high".

    Настрой health_path под свой API (например "/health", "/api/status").
    """

    def __init__(self, servers: list[ServerInfo], interval: int = 300,
                 timeout: float = 10.0, health_path: str = "/health"):
        super().__init__(servers, interval)
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.health_path = health_path

    async def check_one(self, server: ServerInfo) -> ServerResult:
        url = f"https://{server.host}:{server.port}{self.health_path}"
        start = time.monotonic()
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url, ssl=False) as resp:
                    ping_ms = round((time.monotonic() - start) * 1000, 1)
                    if resp.status >= 400:
                        return ServerResult(name=server.name, location=server.location, status="down")

                    try:
                        body = await resp.json(content_type=None)
                    except Exception:
                        body = {}

                    load = body.get("load")
                    uptime = body.get("uptime")
                    if load is not None and load > server.load_warn_pct:
                        status: StatusType = "high"
                    else:
                        status = "ok"

                    return ServerResult(
                        name=server.name,
                        location=server.location,
                        status=status,
                        ping=ping_ms,
                        load=load,
                        uptime=uptime,
                    )
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return ServerResult(name=server.name, location=server.location, status="down")


class StubServerMonitor(ServerMonitor):
    """
    Возвращает фиктивные данные. Используй для разработки когда
    реальных серверов нет или SERVERS_MONITOR_TYPE не задан.
    """

    async def check_one(self, server: ServerInfo) -> ServerResult:
        import random
        load = round(random.uniform(10, 95), 1)
        return ServerResult(
            name=server.name,
            location=server.location,
            status="high" if load > server.load_warn_pct else "ok",
            ping=round(random.uniform(5, 80), 1),
            load=load,
            uptime=round(random.uniform(97, 100), 2),
        )


# ── Фабрика ───────────────────────────────────────────────────────────────────

def make_server_monitor(
    monitor_type: str,
    servers: list[dict],
    interval: int = 300,
    health_path: str = "/health",
) -> ServerMonitor:
    """
    Создаёт монитор по типу из конфига.

    monitor_type: "tcp" | "http" | "stub"
    servers: список словарей с полями ServerInfo
             [{ "name": "Frankfurt-01", "host": "1.2.3.4", "port": 443, "location": "DE" }]
    """
    server_list = [
        ServerInfo(
            name=s["name"],
            host=s.get("host", ""),
            location=s.get("location", ""),
            port=int(s.get("port", 443)),
            load_warn_pct=float(s.get("load_warn_pct", 80)),
        )
        for s in servers
    ]

    if not server_list or monitor_type == "stub":
        if not server_list:
            print("⚠️  SERVERS не заданы — используется StubServerMonitor")
        return StubServerMonitor(server_list or _default_stub_servers(), interval)

    if monitor_type == "tcp":
        return TcpServerMonitor(server_list, interval)

    if monitor_type == "http":
        return HttpServerMonitor(server_list, interval, health_path=health_path)

    raise ValueError(f"Unknown SERVERS_MONITOR_TYPE: {monitor_type!r}. Допустимые: tcp, http, stub")


def _default_stub_servers() -> list[ServerInfo]:
    return [
        ServerInfo("Frankfurt-01", "stub", "DE"),
        ServerInfo("Amsterdam-03", "stub", "NL"),
        ServerInfo("Warsaw-01",    "stub", "PL"),
    ]
