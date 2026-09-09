"""Карточка клиента: профиль и управление аккаунтом через внешнюю API.

Контракт один — CustomerProvider. Свой источник подключается снаружи:
наследуемся, реализуем fetch() и нужные действия, регистрируем через
register_customer_provider(). Ни оркестратор, ни API, ни фронт при этом не
меняются — см. README, раздел «Карточка клиента: подключение своего API».

Провайдер живёт на ВПН-сервис: у каждого своя панель/биллинг, поэтому объект
создаётся на сервис и получает его строку из БД плюс конфиг из пер-сервисной
настройки `customer`.

Набор действий описан декларативно в ACTIONS: форму под действие фронт строит
по этому описанию, поэтому новое действие добавляется правкой одного бэкенда.
"""
import asyncio
import contextvars
import json
import time
from app.redact import redact
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

CUSTOMER_DEFAULTS = {
    # По умолчанию — мок: реальный источник подключается сменой provider.
    "provider": "mock",
    "config": {},
    "cacheTtl": 60,
}


# Имя оператора текущего действия. ContextVar, а не поле объекта: провайдер
# кэшируется на сервис и общий для всех, поэтому два одновременных действия
# разных операторов затирали бы друг другу имя — и в чужой аудит уехало бы не
# то. У ContextVar значение своё в каждой asyncio-задаче.
_OPERATOR: contextvars.ContextVar[str] = contextvars.ContextVar("operator", default="")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Данные ────────────────────────────────────────────────────────────────────

@dataclass
class KeyInfo:
    """Один VPN-ключ клиента."""

    id: str
    name: str = ""
    server: str = ""
    plan: str = ""
    expires_at: str = ""            # ISO или как отдала API — показываем как есть
    traffic_used: float = 0.0       # ГБ
    traffic_limit: float = 0.0      # ГБ, 0 — без лимита
    devices: int | None = 0         # None — источник не знает; в карточке «—»
    active: bool = True

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name or self.id, "server": self.server,
                "plan": self.plan, "expiresAt": self.expires_at,
                "trafficUsed": self.traffic_used, "trafficLimit": self.traffic_limit,
                "devices": self.devices, "active": self.active}


@dataclass
class Referral:
    """Приглашённый клиент."""

    tg_id: str
    name: str = ""
    paid: bool = False              # довёл ли до оплаты
    deposits_total: float = 0.0
    joined_at: str = ""

    def to_dict(self) -> dict:
        return {"tgId": self.tg_id, "name": self.name or self.tg_id, "paid": self.paid,
                "depositsTotal": self.deposits_total, "joinedAt": self.joined_at}


@dataclass
class Payment:
    amount: float = 0.0
    currency: str = "₽"
    date: str = ""
    method: str = ""

    def to_dict(self) -> dict:
        return {"amount": self.amount, "currency": self.currency,
                "date": self.date, "method": self.method}


@dataclass
class ActivityEvent:
    """Одно событие в ленте «Действия»: что произошло с аккаунтом клиента и по
    чьей воле. Источник — внешняя API (оплаты, журнал бота) либо сама панель
    (что сделал оператор в карточке клиента)."""

    at: str = ""                    # ISO; пустое — источник не сказал когда
    kind: str = "user"              # payment | deposit | key | device | user | message | ticket
    title: str = ""
    detail: str = ""
    actor: str = ""                 # оператор, «клиент», «система»
    amount: Optional[float] = None
    currency: str = "₽"
    source: str = ""                # чем добыто: bot_api, audit, panel

    def to_dict(self) -> dict:
        return {"at": self.at, "kind": self.kind, "title": self.title,
                "detail": self.detail, "actor": self.actor,
                "amount": self.amount, "currency": self.currency,
                "source": self.source}


@dataclass
class Device:
    id: str = ""
    name: str = ""
    last_seen: str = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name or self.id, "lastSeen": self.last_seen}


@dataclass
class CustomerProfile:
    """Канонический профиль. Фронт знает только его — как бы ни выглядел ответ
    вашей API, провайдер приводит данные сюда."""

    tg_id: str
    tg_link: str = ""               # ссылка на никнейм, https://t.me/…
    username: str = ""
    name: str = ""
    language: str = ""              # язык интерфейса в ТГ, "ru" / "en"
    status: str = "active"          # active | banned | expired
    group: str = ""                 # тарифная группа / сегмент
    plan: str = ""
    sub_status: str = "active"
    next_payment: str = ""
    trial: str = "none"             # none | active | used
    banned: bool = False
    is_partner: bool = False
    ref_percent: float = 0.0
    ref_balance: float = 0.0
    ref_code: str = ""
    deposits_total: float = 0.0
    deposits: list = field(default_factory=list)         # list[Payment]
    referrals: list = field(default_factory=list)        # list[Referral]
    keys: list = field(default_factory=list)             # list[KeyInfo]
    devices: list = field(default_factory=list)          # list[Device]
    # Ключ, которому принадлежат устройства из devices. Источники отдают список
    # устройств не по клиенту целиком, а по одному ключу — форма отвязки должна
    # знать, по какому, иначе оператор снимет устройство не с того ключа.
    # Пусто — источник не сказал, форма оставляет выбор ключа оператору.
    devices_key_id: str = ""
    traffic_used: float = 0.0                            # суммарно, ГБ
    traffic_limit: float = 0.0
    # Служебное. source пустой по умолчанию — оркестратор проставит имя
    # провайдера, если тот не указал своё.
    source: str = ""
    is_mock: bool = False
    stale: bool = False             # данные из нашего снапшота, API недоступна
    message: str = ""               # причина stale либо предупреждение
    raw: dict = field(default_factory=dict)              # ответ API как есть
    fetched_at: str = ""

    # Производные — считаем здесь, чтобы фронт не повторял арифметику.
    @property
    def referrals_paid(self) -> int:
        return sum(1 for r in self.referrals if r.paid)

    @property
    def referrals_deposits_total(self) -> float:
        return round(sum(r.deposits_total for r in self.referrals), 2)

    def to_dict(self) -> dict:
        return {
            "tgId": self.tg_id,
            "tgLink": self.tg_link or (f"https://t.me/{self.username.lstrip('@')}"
                                       if self.username else ""),
            "username": self.username,
            "name": self.name,
            "language": self.language,
            "status": "banned" if self.banned else self.status,
            "group": self.group,
            "plan": self.plan,
            "subStatus": self.sub_status,
            "nextPayment": self.next_payment,
            "trial": self.trial,
            "banned": self.banned,
            "isPartner": self.is_partner,
            "refPercent": self.ref_percent,
            "refBalance": self.ref_balance,
            "refCode": self.ref_code,
            "depositsTotal": self.deposits_total,
            "deposits": [d.to_dict() for d in self.deposits],
            "referrals": [r.to_dict() for r in self.referrals],
            "referralsPaid": self.referrals_paid,
            "referralsDepositsTotal": self.referrals_deposits_total,
            "keys": [k.to_dict() for k in self.keys],
            "devices": [d.to_dict() for d in self.devices],
            "devicesKeyId": self.devices_key_id,
            "traffic": {"used": self.traffic_used, "total": self.traffic_limit},
            "source": self.source,
            "isMock": self.is_mock,
            "stale": self.stale,
            "message": self.message,
            "fetchedAt": self.fetched_at or _now_iso(),
        }


@dataclass
class ActionResult:
    ok: bool
    message: str = ""
    data: dict = None

    def to_dict(self) -> dict:
        return {"ok": self.ok, "message": self.message, "data": self.data or {}}


# ── Каталог действий ──────────────────────────────────────────────────────────
# Фронт строит форму по этому описанию, а права проверяются по danger. Новое
# действие = строчка здесь + метод в провайдере; трогать фронт не нужно.

@dataclass
class ActionField:
    name: str
    label: str
    type: str = "number"            # number | text | textarea | select | bool | key | device
    default: object = None
    options: str = ""               # ключ из provider.options(): servers | plans
    required: bool = True
    hint: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "label": self.label, "type": self.type,
                "default": self.default, "options": self.options,
                "required": self.required, "hint": self.hint}


@dataclass
class ActionSpec:
    name: str
    method: str                     # метод провайдера
    label: str
    group: str = "profile"          # profile | keys | referrals
    danger: bool = False            # опасное — только админ
    confirm: str = ""               # текст подтверждения, пусто — без него
    fields: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"name": self.name, "label": self.label, "group": self.group,
                "danger": self.danger, "confirm": self.confirm,
                "fields": [f.to_dict() for f in self.fields]}


ACTIONS: list[ActionSpec] = [
    # ── Ключи ────────────────────────────────────────────────────────────────
    ActionSpec("key_issue", "key_issue", "Выдать ключ", group="keys", fields=[
        ActionField("days", "Срок, дней", "number", default=30),
        ActionField("server", "Сервер", "select", options="servers", required=False),
        ActionField("plan", "Тариф", "select", options="plans", required=False),
    ]),
    ActionSpec("key_add_time", "key_add_time", "Изменить срок", group="keys", fields=[
        ActionField("key_id", "Ключ", "key"),
        ActionField("days", "Дней", "number", default=30,
                    hint="Отрицательное число убавляет срок"),
    ]),
    ActionSpec("key_replace", "key_replace", "Заменить ключ", group="keys",
               confirm="Старый ключ перестанет работать. Заменить?", fields=[
        ActionField("key_id", "Ключ", "key"),
    ]),
    ActionSpec("key_delete", "key_delete", "Удалить ключ", group="keys", danger=True,
               confirm="Ключ будет удалён безвозвратно. Удалить?", fields=[
        ActionField("key_id", "Ключ", "key"),
    ]),
    ActionSpec("key_enable", "key_enable", "Включить ключ", group="keys", fields=[
        ActionField("key_id", "Ключ", "key"),
    ]),
    ActionSpec("key_disable", "key_disable", "Выключить ключ", group="keys",
               confirm="Клиент потеряет доступ по этому ключу. Выключить?", fields=[
        ActionField("key_id", "Ключ", "key"),
    ]),
    ActionSpec("key_move", "key_move", "Сменить локацию", group="keys",
               confirm="Ссылка подписки изменится — клиенту придётся взять новую в боте.",
               fields=[
        ActionField("key_id", "Ключ", "key"),
        ActionField("server_id", "Куда перенести", "select", options="servers"),
    ]),
    ActionSpec("device_unlink", "device_unlink", "Отвязать устройство", group="keys",
               fields=[
        ActionField("key_id", "Ключ", "key"),
        ActionField("hwid", "Устройство", "device"),
    ]),
    ActionSpec("devices_reset", "devices_reset", "Сбросить все устройства", group="keys",
               confirm="Все привязки слетят, клиенту придётся подключиться заново.",
               fields=[
        ActionField("key_id", "Ключ", "key"),
    ]),
    # ── Рефералы ─────────────────────────────────────────────────────────────
    ActionSpec("referral_link", "referral_link", "Привязать реферала",
               group="referrals", fields=[
        ActionField("tg_id", "Telegram ID реферала", "text",
                    hint="Клиент станет рефералом этого пользователя"),
    ]),
    ActionSpec("referral_unlink", "referral_unlink", "Отвязать реферала",
               group="referrals", confirm="Отвязать реферала?", fields=[
        ActionField("tg_id", "Telegram ID реферала", "text"),
    ]),
    # ── Профиль ──────────────────────────────────────────────────────────────
    ActionSpec("ban", "ban", "Забанить", danger=True,
               confirm="Клиент потеряет доступ к сервису. Забанить?", fields=[
        ActionField("reason", "Причина", "text", required=False),
    ]),
    ActionSpec("unban", "unban", "Разбанить", danger=True,
               confirm="Вернуть клиенту доступ?"),
    ActionSpec("set_partner", "set_partner", "Партнёрство", danger=True, fields=[
        ActionField("is_partner", "Сделать партнёром", "bool", default=True),
        ActionField("ref_percent", "Реф. процент", "number", required=False),
    ]),
    ActionSpec("set_ref_balance", "set_ref_balance", "Изменить реф. баланс",
               danger=True, fields=[
        ActionField("amount", "Сумма", "number", default=0),
        ActionField("mode", "Как применить", "select", default="delta",
                    options="ref_balance_modes"),
    ]),
    ActionSpec("send_message", "send_message", "Написать в основного бота", fields=[
        ActionField("text", "Сообщение", "textarea",
                    hint="Уйдёт клиенту в бота, который выдаёт ключи"),
    ]),
    # ── Подписка (переехало из прежнего BillingProvider) ──────────────────────
    ActionSpec("renew", "renew_subscription", "Продлить подписку", fields=[
        ActionField("months", "Месяцев", "number", default=1),
    ]),
    ActionSpec("buy_traffic", "buy_traffic", "Докупить трафик", fields=[
        ActionField("gb", "ГБ", "number", default=10),
    ]),
    ActionSpec("reset_key", "reset_key", "Сбросить ключ",
               confirm="Текущий ключ перестанет работать. Сбросить?"),
]

ACTIONS_BY_NAME = {a.name: a for a in ACTIONS}
DANGEROUS = {a.name for a in ACTIONS if a.danger}

# Варианты для полей типа select, которые не зависят от провайдера.
STATIC_OPTIONS = {
    "ref_balance_modes": [{"value": "delta", "label": "Прибавить к текущему"},
                          {"value": "set", "label": "Установить значение"}],
}


class NotSupported(Exception):
    """Провайдер не умеет это действие."""


# ── Контракт ──────────────────────────────────────────────────────────────────

class CustomerProvider(ABC):
    """Источник данных о клиентах для ОДНОГО ВПН-сервиса.

    Точка расширения. Чтобы подключить свою API:

        class MyProvider(CustomerProvider):
            source = "mypanel"
            async def fetch(self, chat_id) -> CustomerProfile: ...
            async def ban(self, chat_id, reason="") -> ActionResult: ...

        register_customer_provider("mypanel", MyProvider)

    Реализовывать нужно только то, что умеет ваша API: список поддерживаемых
    действий вычисляется по переопределённым методам, панель прячет кнопки
    остальных. `service` — строка из таблицы services, `config` — блок config
    из пер-сервисной настройки `customer`.
    """

    source: str = "custom"
    is_mock: bool = False

    def __init__(self, service: dict, config: dict = None):
        self.service = service or {}
        self.config = config or {}

    @property
    def operator(self) -> str:
        """Имя залогиненного в панели человека для текущего действия."""
        return _OPERATOR.get()

    # ── Чтение ────────────────────────────────────────────────────────────────

    @abstractmethod
    async def fetch(self, chat_id: str) -> CustomerProfile:
        """Профиль клиента. Исключения ловит оркестратор — он покажет снапшот
        из нашей БД, а не сломает открытие тикета."""

    async def options(self, chat_id: str) -> dict:
        """Списки для выпадающих полей форм: серверы и тарифы, доступные для
        выдачи ключа. Формат: {"servers": [{"value": …, "label": …}], …}."""
        return {}

    async def activity(self, chat_id: str, limit: int = 100) -> list:
        """Лента действий: оплаты, пополнения, продления, сбросы ключей, баны —
        всё, что случилось с аккаунтом клиента, и его самого, и администраторов.
        Возвращает list[ActivityEvent]. Не умеет источник — NotSupported, и
        вкладка покажет только то, что записала сама панель."""
        raise NotSupported

    # ── Действия ──────────────────────────────────────────────────────────────
    # Базовые реализации только объявляют контракт. Провайдер переопределяет
    # те, что поддерживает его API, — по этому и строится supports().

    async def key_issue(self, chat_id: str, days: int = 30, server: str = "",
                        plan: str = "") -> ActionResult: raise NotSupported
    async def key_add_time(self, chat_id: str, key_id: str, days: int = 0) -> ActionResult: raise NotSupported
    async def key_replace(self, chat_id: str, key_id: str) -> ActionResult: raise NotSupported
    async def key_delete(self, chat_id: str, key_id: str) -> ActionResult: raise NotSupported
    async def key_enable(self, chat_id: str, key_id: str) -> ActionResult: raise NotSupported
    async def key_disable(self, chat_id: str, key_id: str) -> ActionResult: raise NotSupported
    async def key_move(self, chat_id: str, key_id: str, server_id: str = "") -> ActionResult: raise NotSupported
    async def device_unlink(self, chat_id: str, key_id: str, hwid: str = "") -> ActionResult: raise NotSupported
    async def devices_reset(self, chat_id: str, key_id: str) -> ActionResult: raise NotSupported
    async def referral_link(self, chat_id: str, tg_id: str) -> ActionResult: raise NotSupported
    async def referral_unlink(self, chat_id: str, tg_id: str) -> ActionResult: raise NotSupported
    async def ban(self, chat_id: str, reason: str = "") -> ActionResult: raise NotSupported
    async def unban(self, chat_id: str) -> ActionResult: raise NotSupported
    async def set_partner(self, chat_id: str, is_partner: bool = True,
                          ref_percent: float = None) -> ActionResult: raise NotSupported
    async def set_ref_balance(self, chat_id: str, amount: float = 0,
                              mode: str = "delta") -> ActionResult: raise NotSupported
    async def send_message(self, chat_id: str, text: str) -> ActionResult: raise NotSupported
    async def renew_subscription(self, chat_id: str, months: int = 1) -> ActionResult: raise NotSupported
    async def buy_traffic(self, chat_id: str, gb: int = 10) -> ActionResult: raise NotSupported
    async def reset_key(self, chat_id: str) -> ActionResult: raise NotSupported

    # ── Диспетчер ─────────────────────────────────────────────────────────────

    @classmethod
    def implemented_actions(cls) -> list[str]:
        """Действия, под которые в классе есть настоящая реализация."""
        return [a.name for a in ACTIONS
                if getattr(cls, a.method) is not getattr(CustomerProvider, a.method)]

    def supports(self) -> list[str]:
        """То же, но с учётом конфига: если у конкретной установки часть
        эндпоинтов не поднята, их гасят списком `disable`."""
        off = set(self.config.get("disable") or [])
        return [n for n in self.implemented_actions() if n not in off]

    async def execute(self, action: str, chat_id: str, params: dict = None,
                      operator: str = "") -> ActionResult:
        """`operator` — имя залогиненного в панели человека. Внешние API часто
        ведут свой журнал и хотят знать, кто именно нажал кнопку; провайдеры,
        которым это не нужно, просто игнорируют поле."""
        _OPERATOR.set(operator)
        spec = ACTIONS_BY_NAME.get(action)
        if not spec:
            return ActionResult(ok=False, message=f"Неизвестное действие: {action}")
        if action not in self.supports():
            return ActionResult(ok=False, message=f"Источник «{self.source}» не умеет «{spec.label}»")
        # _coerce вне try: его ValueError — это «не заполнено поле», и его
        # отдельно ловит CustomerService, чтобы показать оператору как есть.
        kwargs = _coerce(spec, params or {})
        try:
            return await getattr(self, spec.method)(chat_id, **kwargs)
        except NotSupported:
            return ActionResult(ok=False, message=f"Источник «{self.source}» не умеет «{spec.label}»")
        except Exception as e:
            # Действие обязано ВЕРНУТЬ результат, а не упасть: отказ внешней
            # API («недостаточно средств», «ключ уже на этом сервере») — это
            # нормальный ответ оператору, а не сбой панели.
            print(f"[{self.source}] {action}: {e}")
            return ActionResult(ok=False, message=redact(e)[:200])


def _coerce(spec: ActionSpec, params: dict) -> dict:
    """Привести параметры формы к типам, объявленным в ActionField."""
    out = {}
    for f in spec.fields:
        raw = params.get(f.name, f.default)
        if raw is None or raw == "":
            if f.required and f.default is None:
                raise ValueError(f"Не заполнено поле «{f.label}»")
            if raw is None or raw == "":
                if f.default is None:
                    continue
                raw = f.default
        if f.type == "number":
            try:
                num = float(raw)
            except (TypeError, ValueError):
                raise ValueError(f"«{f.label}»: нужно число")
            out[f.name] = int(num) if float(num).is_integer() else num
        elif f.type == "bool":
            out[f.name] = raw in (True, "true", "1", 1, "on")
        else:
            out[f.name] = str(raw)
    return out


# ── Реестр ────────────────────────────────────────────────────────────────────

_PROVIDERS: dict[str, type[CustomerProvider]] = {}


def register_customer_provider(name: str, cls: type[CustomerProvider]) -> None:
    """Зарегистрировать источник под именем, которое указывается в настройке
    сервиса (`customer.provider`)."""
    if not issubclass(cls, CustomerProvider):
        raise TypeError(f"{cls!r} не наследник CustomerProvider")
    _PROVIDERS[name] = cls


def build_customer_provider(name: str, service: dict,
                            config: dict = None) -> CustomerProvider | None:
    """Создать провайдера по имени. Неизвестное имя — не падаем: возвращаем
    None, оркестратор отдаст снапшот из БД с внятной причиной."""
    cls = _PROVIDERS.get(name)
    return cls(service, config) if cls else None


def known_customer_providers() -> list[dict]:
    """Список зарегистрированных источников — отдаётся в админку, чтобы свой
    провайдер появлялся в выборе без правки фронта."""
    return [{"name": name, "isMock": cls.is_mock,
             "actions": cls.implemented_actions(),
             "description": (cls.__doc__ or "").strip().split("\n")[0]}
            for name, cls in sorted(_PROVIDERS.items())]


# ── Оркестратор ───────────────────────────────────────────────────────────────

class CustomerService:
    """Ходит к провайдеру сервиса, кэширует профиль и не даёт чужой API
    ломать работу панели.

    Кэш нужен, чтобы переключение между тикетами одного клиента не било по
    внешней API на каждый клик; лок — чтобы два одновременных открытия тикета
    не делали два одинаковых запроса.
    """

    def __init__(self, db):
        self.db = db
        self._cache: dict[tuple[int, str], tuple[float, CustomerProfile]] = {}
        self._locks: dict[tuple[int, str], asyncio.Lock] = {}
        # (service_id) → (ключ конфига, провайдер): пересоздаём объект только
        # когда админ поменял настройки.
        self._providers: dict[int, tuple[str, CustomerProvider]] = {}

    # ── Конфиг ────────────────────────────────────────────────────────────────

    async def settings(self, service_id: int) -> dict:
        stored = await self.db.get_setting_json("customer", None, service_id) or {}
        return {**CUSTOMER_DEFAULTS, **stored}

    async def provider_for(self, service: dict) -> CustomerProvider | None:
        cfg = await self.settings(service["id"])
        name = cfg.get("provider") or ""
        config = cfg.get("config") or {}
        key = json.dumps({"p": name, "c": config}, sort_keys=True, ensure_ascii=False)
        cached = self._providers.get(service["id"])
        if cached and cached[0] == key:
            return cached[1]
        provider = build_customer_provider(name, service, config)
        if provider:
            self._providers[service["id"]] = (key, provider)
        else:
            self._providers.pop(service["id"], None)
        return provider

    # ── Чтение ────────────────────────────────────────────────────────────────

    async def profile(self, service: dict, dialog: dict, refresh: bool = False) -> CustomerProfile:
        chat_id = str(dialog["chat_id"])
        key = (service["id"], chat_id)
        ttl = float((await self.settings(service["id"])).get("cacheTtl") or 60)
        if not refresh:
            hit = self._cache.get(key)
            if hit and (time.monotonic() - hit[0]) < ttl:
                return hit[1]
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            # Пока ждали лок, соседний запрос мог уже всё загрузить.
            hit = self._cache.get(key)
            if not refresh and hit and (time.monotonic() - hit[0]) < ttl:
                return hit[1]
            profile = await self._fetch(service, dialog, chat_id)
            # Устаревший снапшот не кэшируем: следующий заход должен снова
            # попробовать живую API, а не ждать конца TTL.
            if not profile.stale:
                self._cache[key] = (time.monotonic(), profile)
            else:
                self._cache.pop(key, None)
            return profile

    async def _fetch(self, service: dict, dialog: dict, chat_id: str) -> CustomerProfile:
        provider = await self.provider_for(service)
        if not provider:
            name = (await self.settings(service["id"])).get("provider") or "—"
            return self._from_snapshot(dialog, f"Источник «{name}» не зарегистрирован")
        try:
            profile = await provider.fetch(chat_id)
        except Exception as e:
            print(f"[customer] {service['slug']} провайдер {provider.source} упал: {e}")
            return self._from_snapshot(dialog, f"{provider.source}: {redact(e)[:200]}")
        profile.source = profile.source or provider.source
        profile.is_mock = profile.is_mock or provider.is_mock
        profile.fetched_at = profile.fetched_at or _now_iso()
        return profile

    def _from_snapshot(self, dialog: dict, reason: str) -> CustomerProfile:
        """Фолбэк: то, что успел прислать n8n вместе с сообщениями. Тикет должен
        открываться даже когда внешняя API лежит."""
        return CustomerProfile(
            tg_id=str(dialog["chat_id"]),
            username=dialog.get("user_username") or "",
            name=dialog.get("user_name") or "",
            plan=dialog.get("user_plan") or "",
            sub_status=dialog.get("user_sub_status") or "active",
            next_payment=dialog.get("user_next_payment") or "",
            traffic_used=float(dialog.get("user_traffic_used") or 0),
            traffic_limit=float(dialog.get("user_traffic_total") or 0),
            deposits=[Payment(amount=_num(dialog.get("last_payment_amount")),
                              date=dialog.get("last_payment_date") or "")]
            if dialog.get("last_payment_amount") else [],
            source="snapshot",
            stale=True,
            message=f"Данные могут устареть — {reason}",
            fetched_at=_now_iso(),
        )

    async def options(self, service: dict, dialog: dict) -> dict:
        provider = await self.provider_for(service)
        opts = dict(STATIC_OPTIONS)
        if not provider:
            return opts
        try:
            opts.update(await provider.options(str(dialog["chat_id"])) or {})
        except Exception as e:
            print(f"[customer] options: {e}")
        return opts

    async def activity(self, service: dict, dialog: dict, limit: int = 100) -> tuple:
        """(события, отчёт об источниках). Отчёт нужен вкладке: если журнал бота
        закрыт скоупом токена, оператор должен видеть, чего он НЕ видит, а не
        решить, что с аккаунтом ничего не происходило."""
        provider = await self.provider_for(service)
        if not provider:
            name = (await self.settings(service["id"])).get("provider") or "—"
            return [], [{"name": name, "ok": False, "error": "источник не зарегистрирован"}]
        try:
            events = await provider.activity(str(dialog["chat_id"]), limit)
        except NotSupported:
            return [], [{"name": provider.source, "ok": False,
                         "error": "источник не умеет отдавать историю действий"}]
        except Exception as e:
            print(f"[customer] activity {provider.source}: {e}")
            return [], [{"name": provider.source, "ok": False, "error": redact(e)[:200]}]
        # Провайдер может вернуть (события, отчёт) — тогда он сам знает, какие
        # его разделы не ответили.
        if isinstance(events, tuple):
            return events
        return events, [{"name": provider.source, "ok": True, "error": ""}]

    async def supports(self, service: dict) -> list[str]:
        provider = await self.provider_for(service)
        return provider.supports() if provider else []

    # ── Действия ──────────────────────────────────────────────────────────────

    async def execute(self, service: dict, dialog: dict, action: str,
                      params: dict, operator: str = "") -> ActionResult:
        provider = await self.provider_for(service)
        if not provider:
            name = (await self.settings(service["id"])).get("provider") or "—"
            return ActionResult(ok=False, message=f"Источник «{name}» не зарегистрирован")
        chat_id = str(dialog["chat_id"])
        try:
            result = await provider.execute(action, chat_id, params, operator=operator)
        except ValueError as e:                      # не прошла валидация формы
            return ActionResult(ok=False, message=redact(e))
        except Exception as e:
            print(f"[customer] действие {action} упало: {e}")
            return ActionResult(ok=False, message=redact(e)[:200])
        if result.ok:
            # Данные изменились — следующий запрос должен идти в API.
            self._cache.pop((service["id"], chat_id), None)
        return result

    def invalidate(self, service_id: int, chat_id: str = None):
        if chat_id is None:
            for key in [k for k in self._cache if k[0] == service_id]:
                self._cache.pop(key, None)
            self._providers.pop(service_id, None)
        else:
            self._cache.pop((service_id, str(chat_id)), None)


def _num(value) -> float:
    """«499 ₽» и «499» одинаково превращаются в число."""
    if value is None:
        return 0.0
    digits = "".join(ch for ch in str(value) if ch.isdigit() or ch in ".,-")
    try:
        return float(digits.replace(",", "."))
    except ValueError:
        return 0.0
