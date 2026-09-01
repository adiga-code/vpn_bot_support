"""Support API Telegram-бота — основной источник данных о клиентах.

REST-интерфейс самого бота, написанный под внешнюю панель поддержки. В отличие
от прямого доступа к VPN-панели, здесь есть всё, что видит бот: балансы,
депозиты, рефералы, промокоды, пробный период, язык — и отправка сообщения
клиенту в тот же чат, где он общается с ботом. В VPN-панель API ходит сам и
отдаёт её данные в полях `panel_*`.

Настройка сервиса → «Клиенты» → источник `bot_api`, config:

    {
      "base_url": "https://host/nemoivpn/api/v1",   // сегмент bot_id свой у каждого
      "token":    "токен этого бота",
      "timeout":  20,
      "notify":   true,        // слать ли клиенту уведомления при действиях
      "default_server_id": null,
      "default_days": 30
    }

Адрес отличается только сегментом `<bot_id>`, поэтому шесть ботов заказчика —
это шесть сервисов в панели, у каждого свой base_url и свой токен. Один токен
на несколько ботов использовать нельзя.

Четыре места, где успешный HTTP-код ещё не означает успех, и провайдер обязан
это разворачивать: `panel_error` в карточке ключа, `delivered` при отправке
сообщения, `ok` в ActionResult и `error` в состоянии сервера.
"""
import asyncio
import json

import aiohttp

from app.customer import (
    ActionResult, ActivityEvent, CustomerProfile, CustomerProvider, Device, KeyInfo,
    Payment, Referral, register_customer_provider,
)


def _day(value) -> str:
    """ISO-дата без времени: в карточке место только под дату."""
    if not value:
        return ""
    return str(value).split("T")[0]


def _num(value) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


class BotApiProvider(CustomerProvider):
    """Support API бота: профиль, балансы, рефералы, ключи и устройства."""

    source = "bot_api"

    # ── Транспорт ─────────────────────────────────────────────────────────────

    async def _request(self, method: str, path: str, *, params=None, json=None):
        base = (self.config.get("base_url") or "").rstrip("/")
        if not base:
            raise RuntimeError("Не указан base_url в настройке «Клиенты» сервиса")
        headers = {"Authorization": f"Bearer {self.config.get('token') or ''}"}
        # Их журнал аудита пишет, кто нажал кнопку. Без заголовка там будет
        # виден только токен, и разобраться, кто из операторов что сделал,
        # не выйдет.
        if self.operator:
            headers["X-Operator"] = self.operator
        timeout = aiohttp.ClientTimeout(total=float(self.config.get("timeout", 20)))
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.request(method, base + path, params=params, json=json,
                                 headers=headers) as r:
                text = await r.text()
                body = {}
                if text:
                    try:
                        body = await r.json(content_type=None)
                    except Exception:
                        body = {}
                if r.status >= 400:
                    raise RuntimeError(self._error_text(r.status, body))
                return body

    @staticmethod
    def _error_text(status: int, body) -> str:
        """Их формат ошибки: {error, status, path}, у валидации ещё details."""
        if not isinstance(body, dict):
            return f"HTTP {status}"
        msg = body.get("error") or f"HTTP {status}"
        details = body.get("details")
        if isinstance(details, list) and details:
            first = details[0]
            if isinstance(first, dict):
                loc = ".".join(str(x) for x in (first.get("loc") or [])[-2:])
                msg = f"{msg}: {loc} — {first.get('msg', '')}".strip()
        return msg

    async def _maybe(self, coro, what: str):
        """Дополнительные разделы карточки не должны ронять её целиком."""
        try:
            return await coro
        except Exception as e:
            print(f"[bot_api] {what}: {e}")
            return None

    # ── Чтение ────────────────────────────────────────────────────────────────

    async def fetch(self, chat_id: str) -> CustomerProfile:
        try:
            u = await self._request("GET", "/users/resolve", params={"value": str(chat_id)})
        except RuntimeError as e:
            # Клиент пишет в поддержку, но в боте его нет — нормальная ситуация,
            # а не сбой: карточка открывается с пояснением.
            if "not found" in str(e).lower() or "не найден" in str(e).lower():
                return CustomerProfile(tg_id=str(chat_id), status="unknown",
                                       message="В боте нет пользователя с таким Telegram ID")
            raise

        # Рефералы и платежи — отдельные разделы; тянем параллельно, они
        # быстрые и в панель не ходят.
        referrals_raw, payments_raw = await asyncio.gather(
            self._maybe(self._request("GET", f"/users/{u['tgid']}/referrals",
                                      params={"limit": 50}), "referrals"),
            self._maybe(self._request("GET", f"/users/{u['tgid']}/payments",
                                      params={"limit": 20}), "payments"),
        )

        keys = [
            KeyInfo(
                id=str(k.get("id")),
                name=k.get("location_name") or k.get("server_name") or str(k.get("id")),
                server=k.get("server_name") or "",
                plan=k.get("location_name") or "",
                expires_at=_day(k.get("expires_at")),
                traffic_used=_num(k.get("traffic_month_gb")),
                # Лимит общий на бота и лежит в /meta, у ключа его нет.
                traffic_limit=0.0,
                # Счётчик устройств есть только в полной карточке ключа, а её
                # мы берём для одного активного. У остальных «не знаем» —
                # честнее нуля, который прочитали бы как «устройств нет».
                devices=None,
                active=bool(k.get("status")) and not k.get("blocked"),
            )
            for k in (u.get("keys") or []) if isinstance(k, dict)
        ]

        # Устройства и живые данные панели есть только в полной карточке ключа,
        # а она ходит в панель дважды и медленная. Берём один активный ключ, а
        # не все подряд — иначе карточка клиента с пятью ключами открывается
        # секундами.
        devices, panel_note = [], ""
        main_key = next((k for k in (u.get("keys") or []) if k.get("status")),
                        (u.get("keys") or [None])[0])
        if main_key:
            detail = await self._maybe(
                self._request("GET", f"/keys/{main_key['id']}"), "key detail")
            if detail:
                devices = [
                    Device(id=str(d.get("hwid") or ""),
                           name=" ".join(x for x in (d.get("platform"), d.get("device_model"),
                                                     d.get("os_version")) if x)
                                or str(d.get("hwid") or ""),
                           last_seen=_day(d.get("created_at")))
                    for d in (detail.get("devices") or []) if isinstance(d, dict)
                ]
                if detail.get("panel_error"):
                    panel_note = f"VPN-панель недоступна: {detail['panel_error']}"
                for k in keys:
                    if k.id == str(detail.get("id")):
                        k.traffic_limit = _num(detail.get("panel_traffic_limit_gb"))
                        if detail.get("panel_traffic_gb"):
                            k.traffic_used = _num(detail["panel_traffic_gb"])
                        k.devices = len(devices)

        referrals = [
            Referral(tg_id=str(r.get("tgid")), name=r.get("fullname") or r.get("username") or "",
                     paid=bool(r.get("has_paid")),
                     deposits_total=_num(r.get("payments_total")),
                     joined_at=_day(r.get("date_registered")))
            for r in ((referrals_raw or {}).get("items") or []) if isinstance(r, dict)
        ]
        deposits = [
            Payment(amount=_num(p.get("amount")), date=_day(p.get("created_at")),
                    method=p.get("payment_system") or "")
            for p in ((payments_raw or {}).get("items") or []) if isinstance(p, dict)
        ]

        active = next((k for k in keys if k.active), keys[0] if keys else None)
        return CustomerProfile(
            tg_id=str(u.get("tgid")),
            username=u.get("username") or "",
            name=u.get("fullname") or "",
            language=u.get("lang") or u.get("lang_tg") or "",
            # Забанен — это blocked (блокировка администратором). Поле banned
            # у них про допуск к боту после капчи, к бану отношения не имеет.
            banned=bool(u.get("blocked")),
            status="banned" if u.get("blocked") else "active",
            group=u.get("group") or "",
            plan=active.plan if active else "",
            sub_status="active" if active else "expired",
            next_payment=active.expires_at if active else "",
            trial="used" if u.get("trial_period_used") else "none",
            is_partner=bool(u.get("referral_percent")),
            ref_percent=_num(u.get("referral_percent")),
            ref_balance=_num(u.get("referral_balance")),
            deposits_total=_num(u.get("payments_total")),
            deposits=deposits,
            referrals=referrals,
            keys=keys,
            devices=devices,
            devices_key_id=str(main_key["id"]) if main_key and devices else "",
            # Месячный расход, а не traffic_gb: тот считает трафик за всё
            # время, а лимит рядом — месячный, и полоса переполнялась бы.
            traffic_used=round(sum(k.traffic_used for k in keys), 2),
            traffic_limit=round(sum(k.traffic_limit for k in keys), 2),
            message=panel_note,
            raw=u,
        )

    async def meta(self) -> dict:
        """`GET /meta` — самый дешёвый запрос, каким проверяют связь: не ходит
        в VPN-панель и сразу показывает, какому боту принадлежит токен и какие
        скоупы выданы."""
        return await self._request("GET", "/meta")

    async def options(self, chat_id: str) -> dict:
        out = {}
        servers = await self._maybe(self._request("GET", "/servers"), "servers")
        if isinstance(servers, list):
            out["servers"] = [
                {"value": str(s.get("id")),
                 "label": f"{s.get('location_name') or s.get('vds_name') or s.get('id')}"
                          f"{'' if s.get('work') else ' (не выдаётся)'}"}
                for s in servers if isinstance(s, dict)
            ]
        return out

    # ── Лента действий ────────────────────────────────────────────────────────

    # Журнал бота пишет продление, сброс и удаление ключа НА КЛЮЧ, а не на
    # пользователя, поэтому одного запроса по target_type=user мало: половина
    # событий, ради которых вкладку и заводили, прошла бы мимо.
    _AUDIT_KEYS_LIMIT = 5

    _AUDIT_TITLES = {
        "balance":       "Изменён баланс",
        "message":       "Отправлено сообщение",
        "extend":        "Изменён срок ключа",
        "enable":        "Ключ включён",
        "disable":       "Ключ выключен",
        "recreate":      "Ключ пересоздан",
        "move":          "Смена локации",
        "trial/reset":   "Пробный период сброшен",
        "approve":       "Выплата подтверждена",
        "reject":        "Выплата отклонена",
    }

    @staticmethod
    def _audit_title(entry: dict) -> str:
        """Человеческое название по методу и хвосту пути: /keys/41155/extend →
        «Изменён срок ключа». Незнакомое действие показываем как есть — лучше
        сырой путь, чем пропущенное событие."""
        path = str(entry.get("path") or "")
        method = str(entry.get("method") or "").upper()
        tail = path.rstrip("/").split("/")
        # Устройства разбираем до словаря: у них путь заканчивается на hwid, а
        # не на действие, и «all» означает сброс всех привязок разом.
        if "devices" in tail:
            return "Отвязаны все устройства" if tail[-1] == "all" else "Отвязано устройство"
        for key, title in BotApiProvider._AUDIT_TITLES.items():
            if path.endswith("/" + key) or ("/" + key + "/") in path:
                return title
        if entry.get("target_type") == "key":
            if method == "DELETE":
                return "Ключ удалён"
            if method == "POST":
                return "Выдан ключ"
        if entry.get("target_type") == "user" and method == "PATCH":
            return "Изменён профиль"
        return f"{method} {path}"

    @staticmethod
    def _audit_detail(entry: dict) -> str:
        """`payload` у них строка с JSON, а не объект. Разворачиваем её в пару
        понятных полей; неразбираемое показываем как есть, обрезав."""
        raw = entry.get("payload")
        if not raw:
            return ""
        try:
            data = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (ValueError, TypeError):
            return str(raw)[:160]
        if not isinstance(data, dict):
            return str(raw)[:160]
        bits = []
        if "delivered" in data:
            bits.append("доставлено" if data["delivered"] else "не доставлено")
        for key, label in (("reason", ""), ("days", "дней"), ("months", "мес."),
                           ("amount", "сумма"), ("old_value", "было"),
                           ("new_value", "стало"), ("detail", "")):
            if data.get(key) not in (None, "", []):
                bits.append(f"{label} {data[key]}".strip())
        return " · ".join(bits)[:200]

    async def _audit(self, params: dict) -> list:
        data = await self._request("GET", "/audit", params={**params, "limit": 50})
        return (data or {}).get("items") or []

    async def activity(self, chat_id: str, limit: int = 100):
        """Оплаты, пополнения баланса и журнал действий бота. Каждый раздел
        добывается отдельно: закрытый скоупом `/audit` не должен уносить с собой
        платежи, а недоступный биллинг — журнал."""
        events: list[ActivityEvent] = []
        sources: list[dict] = []

        def note(name: str, error: str = ""):
            sources.append({"name": name, "ok": not error, "error": error})

        # Ключи нужны, чтобы спросить журнал по каждому из них.
        key_ids = []
        try:
            user = await self._request("GET", "/users/resolve", params={"value": str(chat_id)})
            key_ids = [k.get("id") for k in (user.get("keys") or [])
                       if isinstance(k, dict) and k.get("id")][:self._AUDIT_KEYS_LIMIT]
        except Exception as e:
            note("профиль", str(e)[:160])

        async def payments():
            data = await self._request("GET", f"/users/{chat_id}/payments", params={"limit": 50})
            return (data or {}).get("items") or []

        async def deposits():
            data = await self._request("GET", f"/users/{chat_id}/deposits", params={"limit": 50})
            return (data or {}).get("items") or []

        tasks = [payments(), deposits(),
                 self._audit({"target_type": "user", "target_id": str(chat_id)})]
        tasks += [self._audit({"target_type": "key", "target_id": str(k)}) for k in key_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        pays, deps, audit_user = results[0], results[1], results[2]
        audit_keys = results[3:]

        if isinstance(pays, Exception):
            note("оплаты", str(pays)[:160])
        else:
            note("оплаты")
            for p in pays:
                if not isinstance(p, dict):
                    continue
                months = p.get("month_count")
                events.append(ActivityEvent(
                    at=str(p.get("created_at") or ""), kind="payment",
                    title="Оплата подписки",
                    detail=" · ".join(x for x in (
                        p.get("payment_system") or "",
                        f"{months} мес." if months else "") if x),
                    actor="клиент", amount=_num(p.get("amount")), source="bot_api"))

        if isinstance(deps, Exception):
            note("пополнения", str(deps)[:160])
        else:
            note("пополнения")
            for d in deps:
                if isinstance(d, dict):
                    events.append(ActivityEvent(
                        at=str(d.get("created_at") or ""), kind="deposit",
                        title="Пополнение баланса", actor="клиент",
                        amount=_num(d.get("amount")), source="bot_api"))

        # Журнал: одна ошибка на все запросы — скоуп либо есть, либо нет.
        audit_error = next((str(r) [:160] for r in [audit_user, *audit_keys]
                            if isinstance(r, Exception)), "")
        if audit_error:
            note("журнал бота", audit_error)
        else:
            note("журнал бота")
        seen = set()
        for chunk in [audit_user, *audit_keys]:
            if isinstance(chunk, Exception):
                continue
            for e in chunk:
                if not isinstance(e, dict) or e.get("id") in seen:
                    continue
                seen.add(e.get("id"))
                events.append(ActivityEvent(
                    at=str(e.get("created_at") or ""),
                    kind="key" if e.get("target_type") == "key" else "user",
                    title=self._audit_title(e),
                    detail=self._audit_detail(e),
                    actor=e.get("actor") or e.get("token_name") or "",
                    source="журнал бота"))

        return events, sources

    # ── Хелперы действий ──────────────────────────────────────────────────────

    def _notify(self) -> bool:
        return bool(self.config.get("notify", True))

    def _body(self, reason: str = "", **extra) -> dict:
        body = {"notify": self._notify()}
        if reason:
            body["reason"] = reason
        body.update({k: v for k, v in extra.items() if v is not None})
        return body

    @staticmethod
    def _unwrap(data, success: str) -> ActionResult:
        """У них `ok: false` при HTTP 200 значит, что запись в базе изменена, а
        действие в панели не прошло. Для оператора это неуспех, а не «Готово»."""
        if isinstance(data, dict) and data.get("ok") is False:
            return ActionResult(ok=False,
                                message=data.get("detail") or "панель не отработала")
        # На успехе поля detail в ответе нет вовсе — None здесь такой же «нечего
        # показывать», как пустая строка, и оператор должен увидеть текст успеха,
        # а не пустой тост.
        detail = (data or {}).get("detail") if isinstance(data, dict) else ""
        return ActionResult(ok=True, message=success if detail in (None, "", "ok") else detail)

    # ── Пользователь ──────────────────────────────────────────────────────────

    async def ban(self, chat_id, reason=""):
        await self._request("PATCH", f"/users/{chat_id}",
                            json={"blocked": True, **({"reason": reason} if reason else {})})
        return ActionResult(ok=True, message="Клиент заблокирован")

    async def unban(self, chat_id):
        await self._request("PATCH", f"/users/{chat_id}", json={"blocked": False})
        return ActionResult(ok=True, message="Блокировка снята")

    async def set_partner(self, chat_id, is_partner=True, ref_percent=None):
        # Отдельного флага «партнёр» в API нет; партнёрство здесь — это
        # ненулевой процент реферальных отчислений.
        percent = int(ref_percent) if ref_percent is not None else (15 if is_partner else 0)
        percent = max(0, min(100, percent))
        await self._request("PATCH", f"/users/{chat_id}", json={"referral_percent": percent})
        return ActionResult(ok=True, message=f"Реферальный процент: {percent}%")

    async def set_ref_balance(self, chat_id, amount=0, mode="delta"):
        amount = int(amount)
        if mode == "set":
            # Их API умеет только дельту, поэтому «установить» считаем от
            # текущего значения. Гонок тут не избежать — предупреждаем словами.
            u = await self._request("GET", f"/users/{chat_id}")
            amount -= int(u.get("referral_balance") or 0)
            if amount == 0:
                return ActionResult(ok=True, message="Баланс уже равен указанному")
        data = await self._request("POST", f"/users/{chat_id}/balance",
                                   json=self._body(target="referral_balance", amount=amount))
        return ActionResult(ok=True,
                            message=f"Реф. баланс: {data.get('old_value')} → {data.get('new_value')}")

    async def send_message(self, chat_id, text):
        data = await self._request("POST", f"/users/{chat_id}/message",
                                   json={"text": text, "parse_mode": "none"})
        # Недоставленное сообщение приходит с кодом 200 — для оператора это
        # неуспех, иначе он будет думать, что клиент прочитал.
        if not data.get("delivered"):
            return ActionResult(ok=False,
                                message=data.get("error") or "сообщение не доставлено")
        return ActionResult(ok=True, message="Сообщение отправлено клиенту в бота")

    # ── Ключи ─────────────────────────────────────────────────────────────────

    async def key_issue(self, chat_id, days=30, server="", plan=""):
        days = int(days or self.config.get("default_days", 30))
        body = self._body(tgid=int(chat_id), days=days)
        server_id = server or self.config.get("default_server_id")
        if server_id:
            body["server_id"] = int(server_id)
        data = await self._request("POST", "/keys", json=body)
        res = self._unwrap(data, f"Ключ выдан на {days} дн.")
        key = (data or {}).get("key") or {}
        res.data = {"key_id": key.get("id")}
        return res

    async def key_add_time(self, chat_id, key_id, days=0):
        days = int(days)
        if days == 0:
            return ActionResult(ok=False, message="Ноль дней — нечего менять")
        data = await self._request("POST", f"/keys/{key_id}/extend",
                                   json=self._body(days=days))
        word = "продлён" if days > 0 else "сокращён"
        return self._unwrap(data, f"Срок ключа {word} на {abs(days)} дн.")

    async def renew_subscription(self, chat_id, months=1):
        key_id = await self._main_key_id(chat_id)
        data = await self._request("POST", f"/keys/{key_id}/extend",
                                   json=self._body(months=int(months)))
        return self._unwrap(data, f"Подписка продлена на {months} мес.")

    async def key_replace(self, chat_id, key_id):
        data = await self._request("POST", f"/keys/{key_id}/recreate")
        return self._unwrap(data, "Ключ пересоздан — ссылка подписки изменилась")

    async def key_delete(self, chat_id, key_id):
        data = await self._request("DELETE", f"/keys/{key_id}",
                                   params={"reason": "удалено из панели поддержки"})
        return self._unwrap(data, "Ключ удалён")

    async def key_enable(self, chat_id, key_id):
        data = await self._request("POST", f"/keys/{key_id}/enable", json=self._body())
        return self._unwrap(data, "Ключ включён")

    async def key_disable(self, chat_id, key_id):
        data = await self._request("POST", f"/keys/{key_id}/disable", json=self._body())
        return self._unwrap(data, "Ключ выключен")

    async def key_move(self, chat_id, key_id, server_id=""):
        if not server_id:
            return ActionResult(ok=False, message="Не выбран сервер")
        data = await self._request("POST", f"/keys/{key_id}/move",
                                   json={"server_id": int(server_id),
                                         "reason": "смена локации из панели поддержки"})
        return self._unwrap(data, "Локация изменена — клиенту нужна новая ссылка подписки")

    # ── Устройства ────────────────────────────────────────────────────────────

    async def device_unlink(self, chat_id, key_id, hwid=""):
        if not hwid:
            return ActionResult(ok=False, message="Не выбрано устройство")
        data = await self._request("DELETE", f"/keys/{key_id}/devices/{hwid}")
        return self._unwrap(data, "Устройство отвязано")

    async def devices_reset(self, chat_id, key_id):
        data = await self._request("DELETE", f"/keys/{key_id}/devices/all")
        return self._unwrap(data, "Все устройства отвязаны")

    # ── Общее ─────────────────────────────────────────────────────────────────

    async def _main_key_id(self, chat_id):
        """Ключ, к которому относятся действия без явного выбора."""
        u = await self._request("GET", f"/users/{chat_id}")
        keys = u.get("keys") or []
        if not keys:
            raise RuntimeError("У клиента нет ключей")
        return next((k["id"] for k in keys if k.get("status")), keys[0]["id"])


register_customer_provider("bot_api", BotApiProvider)
