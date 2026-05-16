import asyncio
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import aiohttp

StatusType = Literal["ok", "high", "down", "unknown"]


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class ServerInfo:
    name: str
    host: str                   # IP or hostname
    location: str = ""
    port: int = 443             # port for TCP / HTTP check
    load_warn_pct: float = 80   # load above this threshold → status "high"


@dataclass
class ServerResult:
    name: str
    status: StatusType
    location: str = ""
    ping: float | None = None   # ms
    load: float | None = None   # %
    uptime: float | None = None  # %


# ── Base class ────────────────────────────────────────────────────────────────

class ServerMonitor(ABC):
    """Implement check_one(); the polling loop and snapshot API come for free."""

    def __init__(self, servers: list[ServerInfo], interval: int = 300):
        self.servers = servers
        self.interval = interval
        self._results: list[ServerResult] = []
        self._last_updated: str | None = None

    def get_snapshot(self) -> dict:
        """Return current results in the shape the frontend expects."""
        return {
            "servers": [self._result_to_dict(r) for r in self._results],
            "last_updated": self._last_updated,
        }

    async def run_forever(self):
        """Background polling loop — run via asyncio.gather() in main.py."""
        print(f"Server monitor started ({len(self.servers)} servers, interval={self.interval}s)")
        while True:
            await self._run_check()
            await asyncio.sleep(self.interval)

    @abstractmethod
    async def check_one(self, server: ServerInfo) -> ServerResult: ...

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


# ── Implementations ───────────────────────────────────────────────────────────

class TcpServerMonitor(ServerMonitor):
    """
    Checks reachability via a TCP connection.

    Pros:  works for any TCP port (VPN, SSH, HTTPS).
    Cons:  no load or uptime data — availability and ping only.
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
    Checks a server via HTTP GET to a health endpoint.

    Expected JSON response (fields optional):
        { "load": 42.5, "uptime": 99.9 }

    Status "down" if unreachable or HTTP >= 400.
    Status "high" if load exceeds server.load_warn_pct.
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
                    status: StatusType = (
                        "high" if load is not None and load > server.load_warn_pct else "ok"
                    )
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
    """Returns randomised fake data — use during development when no real servers exist."""

    async def check_one(self, server: ServerInfo) -> ServerResult:
        load = round(random.uniform(10, 95), 1)
        return ServerResult(
            name=server.name,
            location=server.location,
            status="high" if load > server.load_warn_pct else "ok",
            ping=round(random.uniform(5, 80), 1),
            load=load,
            uptime=round(random.uniform(97, 100), 2),
        )


# ── Factory ───────────────────────────────────────────────────────────────────

def make_server_monitor(
    monitor_type: str,
    servers: list[dict],
    interval: int = 300,
    health_path: str = "/health",
) -> ServerMonitor:
    """
    Build a ServerMonitor from the app config.

    monitor_type: "tcp" | "http" | "stub"
    servers: list of dicts with ServerInfo fields, e.g.
             [{"name": "Frankfurt-01", "host": "1.2.3.4", "port": 443, "location": "DE"}]
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
            print("SERVERS not configured — using StubServerMonitor")
        return StubServerMonitor(server_list or _default_stub_servers(), interval)

    if monitor_type == "tcp":
        return TcpServerMonitor(server_list, interval)

    if monitor_type == "http":
        return HttpServerMonitor(server_list, interval, health_path=health_path)

    raise ValueError(f"Unknown SERVERS_MONITOR_TYPE: {monitor_type!r}. Valid values: tcp, http, stub")


def _default_stub_servers() -> list[ServerInfo]:
    return [
        ServerInfo("Frankfurt-01", "stub", "DE"),
        ServerInfo("Amsterdam-03", "stub", "NL"),
        ServerInfo("Warsaw-01",    "stub", "PL"),
    ]
