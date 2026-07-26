"""Готовые источники данных о клиентах: мок и универсальный HTTP-клиент.

Мок работает из коробки и помечен как выдуманный. Настоящая интеграция — это
`http`: у него не зашито ни одного имени поля, соответствие описывается в
конфиге сервиса. Если у вашей API совсем другая логика — наследуйтесь от
CustomerProvider и положите файл в app/providers/.
"""
import random
from datetime import datetime, timedelta, timezone

import aiohttp

from app.customer import (
    ACTIONS_BY_NAME, ActionResult, CustomerProfile, CustomerProvider, Device,
    KeyInfo, Payment, Referral, register_customer_provider,
)


def _iso(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()


# ── Мок ───────────────────────────────────────────────────────────────────────

MOCK_SERVERS = [
    {"value": "fra-01", "label": "Frankfurt-01 · DE"},
    {"value": "ams-02", "label": "Amsterdam-02 · NL"},
    {"value": "sto-01", "label": "Stockholm-01 · SE"},
]
MOCK_PLANS = [
    {"value": "basic", "label": "Basic · 100 ГБ"},
    {"value": "pro", "label": "Pro · 500 ГБ"},
    {"value": "premium", "label": "Premium · безлимит"},
]


class MockCustomerProvider(CustomerProvider):
    """Выдуманные данные (мок) — панель работает без внешней API."""

    source = "mock"
    is_mock = True

    async def fetch(self, chat_id: str) -> CustomerProfile:
        # Один и тот же клиент всегда выглядит одинаково: иначе цифры бы
        # прыгали при каждом обновлении карточки.
        rnd = random.Random(f"{self.service.get('slug', '')}:{chat_id}")
        plan = rnd.choice(["Basic", "Pro", "Premium"])
        limit = {"Basic": 100.0, "Pro": 500.0, "Premium": 0.0}[plan]
        keys = [
            KeyInfo(id=f"key-{chat_id}-{i}", name=f"Ключ {i + 1}",
                    server=rnd.choice(MOCK_SERVERS)["label"].split(" · ")[0],
                    plan=plan, expires_at=_iso(rnd.randint(-5, 300)),
                    traffic_used=round(rnd.uniform(0, 80), 1),
                    traffic_limit=limit, devices=rnd.randint(1, 4),
                    active=i == 0 or rnd.random() > 0.3)
            for i in range(rnd.randint(1, 3))
        ]
        referrals = [
            Referral(tg_id=str(700000000 + rnd.randint(1, 999999)),
                     name=rnd.choice(["Игорь", "Анна", "Марк", "Ольга", "Денис"]),
                     paid=rnd.random() > 0.4,
                     deposits_total=round(rnd.choice([0, 299, 499, 899]), 2),
                     joined_at=_iso(-rnd.randint(10, 300)))
            for _ in range(rnd.randint(0, 5))
        ]
        deposits = [
            Payment(amount=round(rnd.choice([299, 499, 899, 1290]), 2), date=_iso(-30 * i),
                    method=rnd.choice(["Карта", "СБП", "Crypto"]))
            for i in range(rnd.randint(1, 4))
        ]
        return CustomerProfile(
            tg_id=str(chat_id),
            username=f"@user{str(chat_id)[-4:]}",
            name=f"Клиент {str(chat_id)[-4:]}",
            language=rnd.choice(["ru", "en", "uk"]),
            status="active",
            group=rnd.choice(["Обычные", "VIP", "Корпоративные"]),
            plan=plan,
            sub_status=rnd.choice(["active", "active", "expiring"]),
            next_payment=_iso(rnd.randint(1, 60)),
            trial=rnd.choice(["none", "active", "used"]),
            banned=False,
            is_partner=rnd.random() > 0.7,
            ref_percent=rnd.choice([0, 10, 15, 25]),
            ref_balance=round(rnd.uniform(0, 5000), 2),
            ref_code=f"REF{str(chat_id)[-5:]}",
            deposits_total=round(sum(d.amount for d in deposits), 2),
            deposits=deposits,
            referrals=referrals,
            keys=keys,
            devices=[Device(id=f"dev-{i}", name=n, last_seen=_iso(-rnd.randint(0, 14)))
                     for i, n in enumerate(rnd.sample(
                         ["iPhone 15", "Windows 11", "Android TV", "MacBook Air", "iPad"],
                         rnd.randint(1, 3)))],
            # Суммарный расход не должен обгонять лимит тарифа — иначе полоса
            # в карточке всегда выглядит переполненной.
            traffic_used=round(min(sum(k.traffic_used for k in keys), limit or 1e9), 1),
            traffic_limit=limit,
            message="МОК: выдуманные данные, реальный источник не подключён",
        )

    async def options(self, chat_id: str) -> dict:
        return {"servers": MOCK_SERVERS, "plans": MOCK_PLANS}

    # Мок умеет всё — чтобы интерфейс можно было пройти целиком до интеграции.
    def _ok(self, action: str, detail: str = "") -> ActionResult:
        label = ACTIONS_BY_NAME[action].label
        return ActionResult(ok=True, message=f"МОК: {label}{(' — ' + detail) if detail else ''}")

    async def key_issue(self, chat_id, days=30, server="", plan=""):
        return self._ok("key_issue", f"{days} дн., сервер {server or 'любой'}")

    async def key_add_time(self, chat_id, key_id, days=0):
        word = "добавлено" if days >= 0 else "убавлено"
        return self._ok("key_add_time", f"{word} {abs(days)} дн. ключу {key_id}")

    async def key_replace(self, chat_id, key_id):
        return self._ok("key_replace", f"ключ {key_id}")

    async def key_delete(self, chat_id, key_id):
        return self._ok("key_delete", f"ключ {key_id}")

    async def referral_link(self, chat_id, tg_id):
        return self._ok("referral_link", f"tg {tg_id}")

    async def referral_unlink(self, chat_id, tg_id):
        return self._ok("referral_unlink", f"tg {tg_id}")

    async def ban(self, chat_id, reason=""):
        return self._ok("ban", reason)

    async def unban(self, chat_id):
        return self._ok("unban")

    async def set_partner(self, chat_id, is_partner=True, ref_percent=None):
        return self._ok("set_partner", "включено" if is_partner else "выключено")

    async def set_ref_balance(self, chat_id, amount=0, mode="delta"):
        return self._ok("set_ref_balance", f"{mode} {amount}")

    async def send_message(self, chat_id, text):
        return self._ok("send_message", f"«{text[:40]}»")

    async def renew_subscription(self, chat_id, months=1):
        return self._ok("renew", f"{months} мес.")

    async def buy_traffic(self, chat_id, gb=10):
        return self._ok("buy_traffic", f"{gb} ГБ")

    async def reset_key(self, chat_id):
        return self._ok("reset_key")


# ── Универсальный HTTP-клиент ─────────────────────────────────────────────────

_PROFILE_FIELDS = {
    # наше поле → поле по умолчанию в ответе вашей API
    "username": "username", "name": "name", "language": "language",
    "status": "status", "group": "group", "plan": "plan",
    "sub_status": "sub_status", "next_payment": "next_payment",
    "trial": "trial", "banned": "banned", "is_partner": "is_partner",
    "ref_percent": "ref_percent", "ref_balance": "ref_balance",
    "ref_code": "ref_code", "deposits_total": "deposits_total",
    "traffic_used": "traffic_used", "traffic_limit": "traffic_limit",
    "tg_link": "tg_link",
}
_KEY_FIELDS = {"id": "id", "name": "name", "server": "server", "plan": "plan",
               "expires_at": "expires_at", "traffic_used": "traffic_used",
               "traffic_limit": "traffic_limit", "devices": "devices", "active": "active"}
_REFERRAL_FIELDS = {"tg_id": "tg_id", "name": "name", "paid": "paid",
                    "deposits_total": "deposits_total", "joined_at": "joined_at"}
_PAYMENT_FIELDS = {"amount": "amount", "currency": "currency",
                   "date": "date", "method": "method"}

# Пути по умолчанию: {chat_id} подставляется. Переопределяются в config.paths.
_DEFAULT_PATHS = {
    "profile":          "GET /api/customers/{chat_id}",
    "options":          "GET /api/customers/{chat_id}/options",
    "key_issue":        "POST /api/customers/{chat_id}/keys",
    "key_add_time":     "POST /api/customers/{chat_id}/keys/{key_id}/time",
    "key_replace":      "POST /api/customers/{chat_id}/keys/{key_id}/replace",
    "key_delete":       "DELETE /api/customers/{chat_id}/keys/{key_id}",
    "referral_link":    "POST /api/customers/{chat_id}/referrals",
    "referral_unlink":  "DELETE /api/customers/{chat_id}/referrals/{tg_id}",
    "ban":              "POST /api/customers/{chat_id}/ban",
    "unban":            "POST /api/customers/{chat_id}/unban",
    "set_partner":      "POST /api/customers/{chat_id}/partner",
    "set_ref_balance":  "POST /api/customers/{chat_id}/ref_balance",
    "send_message":     "POST /api/customers/{chat_id}/message",
    "renew":            "POST /api/customers/{chat_id}/subscription/renew",
    "buy_traffic":      "POST /api/customers/{chat_id}/subscription/traffic",
    "reset_key":        "POST /api/customers/{chat_id}/keys/reset",
}


class HttpCustomerProvider(CustomerProvider):
    """Ваша REST API: профиль клиента и управление аккаунтом.

    Конфиг (в пер-сервисной настройке `customer`, поле config):

        {
          "base_url":    "https://infra.example.com",
          "token":       "секрет",
          "auth_header": "Authorization",      # или "X-API-Key" — тогда без Bearer
          "service_param": "service",          # чем фильтровать по ВПН-у
          "timeout": 10,

          # Пути, если отличаются от умолчаний. Формат «МЕТОД /путь»,
          # {chat_id}, {key_id}, {tg_id} подставляются.
          "paths": {"profile": "GET /v2/users/{chat_id}"},

          # Соответствие имён полей: наше → ваше.
          "mapping":  {"ref_balance": "referral_balance", "plan": "tariff"},
          "keys_field": "keys", "referrals_field": "referrals",
          "deposits_field": "payments",
          "keys_mapping":      {"expires_at": "valid_until"},
          "referrals_mapping": {"tg_id": "telegram_id"},
          "deposits_mapping":  {"amount": "sum"},

          # Что ваша API не умеет — гасится, кнопки не показываются.
          "disable": ["set_partner"]
        }
    """

    source = "http"

    # ── Транспорт ─────────────────────────────────────────────────────────────

    def _url(self, path: str) -> str:
        return (self.config.get("base_url") or "").rstrip("/") + path

    def _headers(self) -> dict:
        token = self.config.get("token")
        if not token:
            return {}
        header = self.config.get("auth_header", "Authorization")
        return {header: f"Bearer {token}" if header.lower() == "authorization" else token}

    def _route(self, action: str, **fmt) -> tuple[str, str]:
        raw = (self.config.get("paths") or {}).get(action) or _DEFAULT_PATHS[action]
        method, _, path = raw.partition(" ")
        return method.upper(), path.format(**fmt)

    async def _call(self, action: str, payload: dict = None, **fmt):
        if not self.config.get("base_url"):
            raise RuntimeError("Не указан base_url в настройке «Клиенты» сервиса")
        method, path = self._route(action, **fmt)
        params = {}
        param = self.config.get("service_param", "service")
        if param:
            params[param] = self.service.get("slug", "")
        timeout = aiohttp.ClientTimeout(total=float(self.config.get("timeout", 10)))
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.request(method, self._url(path), params=params,
                                 json=payload if method != "GET" else None,
                                 headers=self._headers()) as r:
                body = await r.json(content_type=None) if r.content_length != 0 else {}
                if r.status >= 400:
                    msg = ""
                    if isinstance(body, dict):
                        msg = body.get("error") or body.get("message") or ""
                    raise RuntimeError(msg or f"HTTP {r.status}")
                return body if isinstance(body, (dict, list)) else {}

    async def _act(self, action: str, payload: dict = None, **fmt) -> ActionResult:
        try:
            body = await self._call(action, payload, **fmt)
        except Exception as e:
            return ActionResult(ok=False, message=str(e)[:200])
        message = ""
        if isinstance(body, dict):
            message = body.get("message") or ""
        return ActionResult(ok=True, message=message or ACTIONS_BY_NAME[action].label,
                            data=body if isinstance(body, dict) else {})

    # ── Чтение ────────────────────────────────────────────────────────────────

    async def fetch(self, chat_id: str) -> CustomerProfile:
        raw = await self._call("profile", chat_id=chat_id)
        if not isinstance(raw, dict):
            raise RuntimeError("Ответ профиля не объект")
        # Часть API заворачивает полезную нагрузку — разворачиваем.
        for wrapper in ("data", "user", "customer", "result"):
            if isinstance(raw.get(wrapper), dict):
                raw = raw[wrapper]
                break

        fields = {**_PROFILE_FIELDS, **(self.config.get("mapping") or {})}
        get = lambda key, default=None: raw.get(fields.get(key, key), default)  # noqa: E731

        keys = [KeyInfo(**_pick(item, _KEY_FIELDS, self.config.get("keys_mapping"),
                               {"traffic_used": float, "traffic_limit": float,
                                "devices": int, "active": bool, "id": str}))
                for item in _list_of(raw, self.config.get("keys_field", "keys"))]
        referrals = [Referral(**_pick(item, _REFERRAL_FIELDS,
                                      self.config.get("referrals_mapping"),
                                      {"tg_id": str, "paid": bool, "deposits_total": float}))
                     for item in _list_of(raw, self.config.get("referrals_field", "referrals"))]
        deposits = [Payment(**_pick(item, _PAYMENT_FIELDS,
                                    self.config.get("deposits_mapping"),
                                    {"amount": float}))
                    for item in _list_of(raw, self.config.get("deposits_field", "deposits"))]

        return CustomerProfile(
            tg_id=str(chat_id),
            tg_link=str(get("tg_link") or ""),
            username=str(get("username") or ""),
            name=str(get("name") or ""),
            language=str(get("language") or ""),
            status=str(get("status") or "active"),
            group=str(get("group") or ""),
            plan=str(get("plan") or ""),
            sub_status=str(get("sub_status") or "active"),
            next_payment=str(get("next_payment") or ""),
            trial=str(get("trial") or "none"),
            banned=bool(get("banned", False)),
            is_partner=bool(get("is_partner", False)),
            ref_percent=_f(get("ref_percent")),
            ref_balance=_f(get("ref_balance")),
            ref_code=str(get("ref_code") or ""),
            deposits_total=_f(get("deposits_total")) or round(sum(d.amount for d in deposits), 2),
            deposits=deposits,
            referrals=referrals,
            keys=keys,
            devices=[Device(id=str(d.get("id", "")), name=str(d.get("name", "")),
                            last_seen=str(d.get("last_seen", "")))
                     for d in _list_of(raw, "devices")],
            traffic_used=_f(get("traffic_used")) or round(sum(k.traffic_used for k in keys), 1),
            traffic_limit=_f(get("traffic_limit")),
            raw=raw,
        )

    async def options(self, chat_id: str) -> dict:
        try:
            body = await self._call("options", chat_id=chat_id)
        except Exception:
            return {}
        out = {}
        for key in ("servers", "plans"):
            items = body.get(key) if isinstance(body, dict) else None
            if isinstance(items, list):
                out[key] = [x if isinstance(x, dict) and "value" in x
                            else {"value": str(x), "label": str(x)} for x in items]
        return out

    # ── Действия ──────────────────────────────────────────────────────────────

    async def key_issue(self, chat_id, days=30, server="", plan=""):
        return await self._act("key_issue", {"days": days, "server": server, "plan": plan},
                               chat_id=chat_id)

    async def key_add_time(self, chat_id, key_id, days=0):
        return await self._act("key_add_time", {"days": days}, chat_id=chat_id, key_id=key_id)

    async def key_replace(self, chat_id, key_id):
        return await self._act("key_replace", {}, chat_id=chat_id, key_id=key_id)

    async def key_delete(self, chat_id, key_id):
        return await self._act("key_delete", {}, chat_id=chat_id, key_id=key_id)

    async def referral_link(self, chat_id, tg_id):
        return await self._act("referral_link", {"tg_id": tg_id}, chat_id=chat_id, tg_id=tg_id)

    async def referral_unlink(self, chat_id, tg_id):
        return await self._act("referral_unlink", {"tg_id": tg_id}, chat_id=chat_id, tg_id=tg_id)

    async def ban(self, chat_id, reason=""):
        return await self._act("ban", {"reason": reason}, chat_id=chat_id)

    async def unban(self, chat_id):
        return await self._act("unban", {}, chat_id=chat_id)

    async def set_partner(self, chat_id, is_partner=True, ref_percent=None):
        payload = {"is_partner": is_partner}
        if ref_percent is not None:
            payload["ref_percent"] = ref_percent
        return await self._act("set_partner", payload, chat_id=chat_id)

    async def set_ref_balance(self, chat_id, amount=0, mode="delta"):
        return await self._act("set_ref_balance", {"amount": amount, "mode": mode},
                               chat_id=chat_id)

    async def send_message(self, chat_id, text):
        return await self._act("send_message", {"text": text}, chat_id=chat_id)

    async def renew_subscription(self, chat_id, months=1):
        return await self._act("renew", {"months": months}, chat_id=chat_id)

    async def buy_traffic(self, chat_id, gb=10):
        return await self._act("buy_traffic", {"gb": gb}, chat_id=chat_id)

    async def reset_key(self, chat_id):
        return await self._act("reset_key", {}, chat_id=chat_id)


# ── Хелперы разбора ───────────────────────────────────────────────────────────

def _f(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _list_of(raw: dict, key: str) -> list[dict]:
    items = raw.get(key)
    return [x for x in items if isinstance(x, dict)] if isinstance(items, list) else []


def _pick(item: dict, defaults: dict, override: dict, casts: dict) -> dict:
    """Собрать kwargs датакласса из чужого объекта по карте полей."""
    fields = {**defaults, **(override or {})}
    out = {}
    for ours, theirs in fields.items():
        value = item.get(theirs)
        if value is None:
            continue
        cast = casts.get(ours)
        try:
            out[ours] = cast(value) if cast else str(value)
        except (TypeError, ValueError):
            continue
    return out


register_customer_provider("mock", MockCustomerProvider)
register_customer_provider("http", HttpCustomerProvider)
