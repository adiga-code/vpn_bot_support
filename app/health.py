"""Мониторинг состояния по каждому ВПН-сервису: серверы и боты.

Контракт один — HealthProvider. Источник данных подключается снаружи:
наследуемся, реализуем check(), регистрируем через register_provider(). Ни
оркестратор, ни API, ни фронт при этом не меняются — см. README, раздел
«Мониторинг: свой источник данных».

Провайдер живёт в паре (сервис, вид компонента): у каждого ВПН-а свои серверы и
свои боты, поэтому объект провайдера создаётся на сервис и получает его строку
из БД плюс собственный конфиг из пер-сервисной настройки `monitoring`.
"""
import asyncio
import json
from app.redact import redact
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

# ok      — всё в порядке
# high    — работает, но на пределе (высокая нагрузка, очередь апдейтов растёт)
# down    — не отвечает
# unknown — проверить не удалось (провайдер упал, нет конфига)
StatusType = str

SERVERS = "servers"
BOTS = "bots"

MONITORING_DEFAULTS = {
    "interval": 300,
    # По умолчанию — мок: реальные источники подключаются сменой provider.
    SERVERS: {"provider": "mock", "config": {}},
    BOTS:    {"provider": "mock_bot", "config": {}},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Данные ────────────────────────────────────────────────────────────────────

@dataclass
class ComponentStatus:
    """Одна карточка на экране «Состояние» — сервер или бот."""

    id: str                       # уникален в пределах сервиса
    name: str
    kind: str = SERVERS           # SERVERS | BOTS
    status: StatusType = "unknown"
    source: str = "custom"        # чем получено: mock | tcp | http | telegram | своё
    is_mock: bool = False
    location: str = ""
    # server: ping / load / uptime; bot: mode / pending_updates / last_update
    metrics: dict = field(default_factory=dict)
    message: str = ""             # человекочитаемая причина для high/down/unknown
    checked_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "status": self.status,
            "source": self.source,
            "isMock": self.is_mock,
            "location": self.location,
            "metrics": self.metrics,
            "message": self.message,
            "checkedAt": self.checked_at or _now_iso(),
        }


# ── Контракт ──────────────────────────────────────────────────────────────────

class HealthProvider(ABC):
    """Источник состояния для ОДНОГО сервиса.

    Точка расширения. Чтобы подключить свою панель/API:

        class MyProvider(HealthProvider):
            kind, source = "servers", "mypanel"
            async def check(self) -> list[ComponentStatus]: ...

        register_provider("mypanel", MyProvider)

    `service` — строка из таблицы services (slug, name, …), `config` — блок
    config из пер-сервисной настройки monitoring.
    """

    kind: str = SERVERS
    source: str = "custom"
    is_mock: bool = False

    def __init__(self, service: dict, config: dict = None):
        self.service = service or {}
        self.config = config or {}

    @abstractmethod
    async def check(self) -> list[ComponentStatus]:
        """Вернуть текущее состояние. Исключения ловит оркестратор — падение
        одного провайдера не должно ронять опрос остальных."""

    # Хелпер для реализаций: проставляет source/is_mock/checked_at, чтобы
    # каждый провайдер не повторял это в каждой карточке.
    def make(self, id: str, name: str, status: StatusType, **kw) -> ComponentStatus:
        kw.setdefault("kind", self.kind)
        kw.setdefault("source", self.source)
        kw.setdefault("is_mock", self.is_mock)
        return ComponentStatus(id=id, name=name, status=status, checked_at=_now_iso(), **kw)


# ── Реестр ────────────────────────────────────────────────────────────────────

_PROVIDERS: dict[str, type[HealthProvider]] = {}


def register_provider(name: str, cls: type[HealthProvider]) -> None:
    """Зарегистрировать источник данных под именем, которое указывается в
    настройках сервиса (`monitoring.servers.provider`)."""
    if not issubclass(cls, HealthProvider):
        raise TypeError(f"{cls!r} не наследник HealthProvider")
    _PROVIDERS[name] = cls


def build_provider(name: str, service: dict, config: dict = None) -> HealthProvider | None:
    """Создать провайдера по имени. Неизвестное имя — не падаем: возвращаем
    None, оркестратор покажет компонент со статусом unknown и внятной причиной."""
    cls = _PROVIDERS.get(name)
    return cls(service, config) if cls else None


def load_plugins(package: str = "app.providers") -> list[str]:
    """Импортировать все модули из app/providers/ — свой источник данных
    подключается просто файлом в этом каталоге, без правки кода приложения.
    Модуль сам вызывает register_provider() либо register_customer_provider()
    при импорте: каталог общий для мониторинга и карточки клиента."""
    import importlib
    import pkgutil

    loaded = []
    try:
        pkg = importlib.import_module(package)
    except ModuleNotFoundError:
        return loaded
    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"{package}.{mod.name}")
            loaded.append(mod.name)
        except Exception as e:
            print(f"[providers] плагин {mod.name} не загружен: {e}")
    if loaded:
        print(f"[providers] подключены свои источники: {', '.join(loaded)}")
    return loaded


def known_providers(kind: str = None) -> list[dict]:
    """Список зарегистрированных источников — отдаётся в админку, чтобы было из
    чего выбирать без правки фронта при добавлении своего провайдера."""
    out = []
    for name, cls in sorted(_PROVIDERS.items()):
        if kind and cls.kind != kind:
            continue
        out.append({"name": name, "kind": cls.kind, "isMock": cls.is_mock,
                    "description": (cls.__doc__ or "").strip().split("\n")[0]})
    return out


# ── Оркестратор ───────────────────────────────────────────────────────────────

class ServiceHealthMonitor:
    """Опрашивает провайдеров всех активных сервисов и держит снимок состояния.

    Кэш нужен, чтобы экран открывался мгновенно: HTTP-проверка десятка серверов
    занимает секунды, и делать её на каждый запрос страницы нельзя.
    """

    def __init__(self, db, on_component_down: Optional[Callable[..., Awaitable]] = None):
        self.db = db
        self._on_component_down = on_component_down
        self._snapshots: dict[int, dict] = {}
        # (service_id, kind) → (ключ конфига, провайдер): пересоздаём объект
        # только когда админ поменял настройки, а не на каждой итерации.
        self._cache: dict[tuple[int, str], tuple[str, HealthProvider]] = {}
        self._prev: dict[tuple[int, str], str] = {}  # (service_id, component id) → статус
        # Опросы одного сервиса не должны идти параллельно: иначе два
        # одновременных refresh (фоновый цикл + кнопка «Обновить») прочитают
        # один и тот же прошлый статус и оба пошлют уведомление о падении.
        self._locks: dict[int, asyncio.Lock] = {}

    # ── Конфиг ────────────────────────────────────────────────────────────────

    async def _monitoring(self, service_id: int) -> dict:
        stored = await self.db.get_setting_json("monitoring", None, service_id) or {}
        return {**MONITORING_DEFAULTS, **stored}

    def _provider_for(self, service: dict, kind: str, block: dict) -> HealthProvider | None:
        name = (block or {}).get("provider") or ""
        config = (block or {}).get("config") or {}
        key = json.dumps({"p": name, "c": config}, sort_keys=True, ensure_ascii=False)
        cached = self._cache.get((service["id"], kind))
        if cached and cached[0] == key:
            return cached[1]
        provider = build_provider(name, service, config)
        if provider:
            self._cache[(service["id"], kind)] = (key, provider)
        else:
            self._cache.pop((service["id"], kind), None)
        return provider

    # ── Опрос ─────────────────────────────────────────────────────────────────

    async def refresh(self, service: dict) -> dict:
        """Опросить один сервис и обновить его снимок."""
        lock = self._locks.setdefault(service["id"], asyncio.Lock())
        async with lock:
            return await self._refresh_locked(service)

    async def _refresh_locked(self, service: dict) -> dict:
        monitoring = await self._monitoring(service["id"])
        result = {"serviceId": service["id"], "serviceName": service["name"],
                  "serviceSlug": service["slug"], "serviceColor": service.get("color"),
                  "lastUpdated": _now_iso()}
        mock_by_kind = {}
        for kind in (SERVERS, BOTS):
            block = monitoring.get(kind) or {}
            components = await self._check_kind(service, kind, block)
            result[kind] = [c.to_dict() for c in components]
            mock_by_kind[kind] = any(c.is_mock for c in components)
        # Раздельно по серверам и ботам — иначе подключённый Remnawave не
        # спасает от баннера «всё выдумано», пока боты остаются на моке.
        result["serversMock"] = mock_by_kind[SERVERS]
        result["botsMock"] = mock_by_kind[BOTS]
        result["isMock"] = mock_by_kind[SERVERS] or mock_by_kind[BOTS]
        self._snapshots[service["id"]] = result
        await self._notify_new_downs(service, result)
        return result

    async def _check_kind(self, service: dict, kind: str, block: dict) -> list[ComponentStatus]:
        name = (block or {}).get("provider") or "—"
        provider = self._provider_for(service, kind, block)
        if not provider:
            return [ComponentStatus(
                id=f"{kind}-unconfigured", name="Источник не настроен", kind=kind,
                status="unknown", source=name,
                message=f"Провайдер «{name}» не зарегистрирован", checked_at=_now_iso(),
            )]
        try:
            return await provider.check()
        except Exception as e:
            print(f"[health] {service['slug']}/{kind} провайдер {name} упал: {e}")
            return [ComponentStatus(
                id=f"{kind}-error", name="Ошибка опроса", kind=kind, status="unknown",
                source=name, message=redact(e)[:200], checked_at=_now_iso(),
            )]

    async def _notify_new_downs(self, service: dict, snapshot: dict):
        """Уведомляем только на переходе в down — иначе лежащий сервер спамил бы
        уведомлением каждый цикл."""
        if not self._on_component_down:
            return
        for kind in (SERVERS, BOTS):
            for c in snapshot.get(kind, []):
                key = (service["id"], c["id"])
                prev = self._prev.get(key)
                if c["status"] == "down" and prev not in ("down", None):
                    try:
                        await self._on_component_down(service, c)
                    except Exception as e:
                        print(f"[health] on_component_down error: {e}")
                self._prev[key] = c["status"]

    # ── Чтение ────────────────────────────────────────────────────────────────

    def snapshot(self, service_ids: list[int]) -> list[dict]:
        """Снимки по доступным оператору сервисам, в порядке переданных id."""
        return [self._snapshots[sid] for sid in service_ids if sid in self._snapshots]

    async def ensure(self, service: dict) -> dict:
        """Снимок сервиса; если его ещё нет (первый запрос до первого цикла) —
        опросить прямо сейчас."""
        return self._snapshots.get(service["id"]) or await self.refresh(service)

    # ── Фоновый цикл ──────────────────────────────────────────────────────────

    async def run_forever(self):
        print("Health monitor started")
        while True:
            interval = 300
            try:
                services = await self.db.get_services()
                for service in services:
                    monitoring = await self._monitoring(service["id"])
                    interval = min(interval, int(monitoring.get("interval") or 300))
                    await self.refresh(service)
                # Сервис удалили — выкидываем его снимок и провайдеров.
                alive = {s["id"] for s in services}
                for sid in list(self._snapshots):
                    if sid not in alive:
                        self._snapshots.pop(sid, None)
                for key in [k for k in self._cache if k[0] not in alive]:
                    self._cache.pop(key, None)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"[health] цикл опроса: {e}")
            await asyncio.sleep(max(10, interval))
