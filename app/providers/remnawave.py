"""Remnawave как источник данных о клиентах.

Панель управления Xray-подписками: пользователи, трафик, сроки, устройства,
ноды. Денег и партнёрки в её API нет — ни рефералов, ни баланса, ни депозитов,
ни языка и пробного периода. Соответствующие методы здесь НЕ переопределены,
поэтому карточка не покажет эти кнопки, а поля останутся пустыми: пустое поле
честнее выдуманного нуля. Когда появится API бота-магазина, недостающее
подключается вторым источником.

Настройка сервиса → «Клиенты» → источник `remnawave`, config:

    {
      "base_url": "https://panel.example.com",
      "token":    "токен из /api/tokens",
      "timeout":  10,

      // Чем фильтровать список пользователей по Telegram ID. Если ваша сборка
      // ждёт другое имя колонки — поменяйте здесь, поиск сразу заработает.
      "telegram_filter": "telegramId",
      // Как сериализовать фильтр: "brackets" (filters[0][id]=…) или "json".
      "filter_style": "brackets",

      // Для выдачи ключа, когда оператор не выбрал явно.
      "default_days": 30,
      "default_squad_uuid": ""
    }
"""
from datetime import datetime, timedelta, timezone

import aiohttp

from app.customer import (
    ActionResult, CustomerProfile, CustomerProvider, Device, KeyInfo,
    register_customer_provider,
)

GB = 1024 ** 3

# Статусы Remnawave → наши. LIMITED — исчерпан трафик, EXPIRED — вышел срок;
# для оператора это не бан, а именно «неактивен».
_STATUS = {"ACTIVE": "active", "DISABLED": "banned",
           "LIMITED": "limited", "EXPIRED": "expired"}


def _gb(value) -> float:
    """Байты → ГБ. Remnawave считает всё в байтах, карточка — в гигабайтах."""
    try:
        return round(float(value) / GB, 2)
    except (TypeError, ValueError):
        return 0.0


def _day(value) -> str:
    """ISO-дата без времени: в карточке место только под дату."""
    if not value:
        return ""
    return str(value).split("T")[0]


class RemnawaveProvider(CustomerProvider):
    """Remnawave: подписки, трафик, сроки и устройства."""

    source = "remnawave"

    # ── Транспорт ─────────────────────────────────────────────────────────────

    async def _request(self, method: str, path: str, *, params=None, json=None):
        base = (self.config.get("base_url") or "").rstrip("/")
        if not base:
            raise RuntimeError("Не указан base_url в настройке «Клиенты» сервиса")
        token = self.config.get("token") or ""
        timeout = aiohttp.ClientTimeout(total=float(self.config.get("timeout", 10)))
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.request(method, base + path, params=params, json=json,
                                 headers=headers) as r:
                body = await r.json(content_type=None) if r.content_length != 0 else {}
                if r.status >= 400:
                    msg = ""
                    if isinstance(body, dict):
                        msg = body.get("message") or body.get("error") or ""
                    if r.status in (401, 403):
                        msg = msg or "токен не принят или у него нет нужного скоупа"
                    raise RuntimeError(msg or f"HTTP {r.status}")
                # Remnawave заворачивает полезную нагрузку в response.
                if isinstance(body, dict) and "response" in body:
                    return body["response"]
                return body

    # ── Пользователи ──────────────────────────────────────────────────────────

    def _filter_params(self, chat_id: str) -> dict:
        """Фильтр списка по Telegram ID. Точное имя поля зависит от сборки —
        вынесено в конфиг, потому что ошибка здесь тихая: список приходит
        пустым, как будто клиента нет."""
        field = self.config.get("telegram_filter", "telegramId")
        if self.config.get("filter_style") == "json":
            import json as _json
            return {"filters": _json.dumps([{"id": field, "value": str(chat_id)}])}
        return {"filters[0][id]": field, "filters[0][value]": str(chat_id)}

    async def _users(self, chat_id: str) -> list[dict]:
        data = await self._request("GET", "/api/users", params=self._filter_params(chat_id))
        if isinstance(data, list):
            return [u for u in data if isinstance(u, dict)]
        if isinstance(data, dict):
            for key in ("users", "items", "data"):
                if isinstance(data.get(key), list):
                    return [u for u in data[key] if isinstance(u, dict)]
        return []

    async def _first_user(self, chat_id: str) -> dict:
        """Пользователь, над которым выполняется действие: активный, иначе
        первый попавшийся. Действия из карточки без явного key_id относятся
        к нему."""
        users = await self._users(chat_id)
        if not users:
            raise RuntimeError(f"В Remnawave нет пользователя с Telegram ID {chat_id}")
        for u in users:
            if u.get("status") == "ACTIVE":
                return u
        return users[0]

    async def _devices(self, user_id) -> list[Device]:
        try:
            data = await self._request("GET", f"/api/hwid/devices/{user_id}")
        except Exception:
            return []          # устройства — не повод ронять всю карточку
        items = data.get("devices") if isinstance(data, dict) else data
        if not isinstance(items, list):
            return []
        return [Device(id=str(d.get("hwid") or d.get("id") or ""),
                       name=" ".join(x for x in (d.get("platform"), d.get("deviceModel"),
                                                 d.get("osVersion")) if x)
                            or str(d.get("hwid") or ""),
                       last_seen=_day(d.get("updatedAt") or d.get("createdAt")))
                for d in items if isinstance(d, dict)]

    # ── Чтение ────────────────────────────────────────────────────────────────

    async def fetch(self, chat_id: str) -> CustomerProfile:
        users = await self._users(chat_id)
        if not users:
            # Клиент пишет в поддержку, но в панели его нет — это нормальная
            # ситуация (не купил ещё), а не ошибка.
            return CustomerProfile(
                tg_id=str(chat_id),
                status="unknown",
                message="В Remnawave нет пользователя с таким Telegram ID",
            )

        # «Ключ» в карточке = пользователь Remnawave: у каждого свой срок,
        # трафик и ссылка на подписку. Несколько подписок на один Telegram —
        # несколько записей, они и станут списком ключей.
        keys = [
            KeyInfo(
                id=str(u.get("id")),
                name=u.get("username") or str(u.get("id")),
                server=", ".join(s.get("name", "") for s in (u.get("activeInternalSquads") or [])
                                 if isinstance(s, dict)) or "—",
                plan=u.get("tag") or "",
                expires_at=_day(u.get("expireAt")),
                traffic_used=_gb((u.get("userTraffic") or {}).get("usedTrafficBytes")),
                traffic_limit=_gb(u.get("trafficLimitBytes")),
                devices=int(u.get("hwidDeviceLimit") or 0),
                active=u.get("status") == "ACTIVE",
            )
            for u in users
        ]

        main = next((u for u in users if u.get("status") == "ACTIVE"), users[0])
        status = _STATUS.get(main.get("status"), "active")
        devices = await self._devices(main.get("id"))

        return CustomerProfile(
            tg_id=str(chat_id),
            username=main.get("username") or "",
            name=main.get("description") or main.get("username") or "",
            status=status,
            banned=main.get("status") == "DISABLED",
            group=main.get("externalSquadUuid") or "",
            plan=main.get("tag") or ", ".join(
                s.get("name", "") for s in (main.get("activeInternalSquads") or [])
                if isinstance(s, dict)),
            sub_status=status,
            next_payment=_day(main.get("expireAt")),
            # Суммарно по всем подпискам — оператор смотрит на клиента целиком.
            traffic_used=round(sum(k.traffic_used for k in keys), 2),
            traffic_limit=round(sum(k.traffic_limit for k in keys), 2),
            keys=keys,
            devices=devices,
            raw=main,
        )

    async def options(self, chat_id: str) -> dict:
        """Списки для формы выдачи ключа. Падение не критично — форма просто
        останется с пустыми выпадающими списками."""
        out = {}
        try:
            squads = await self._request("GET", "/api/internal-squads")
            items = squads.get("internalSquads") if isinstance(squads, dict) else squads
            if isinstance(items, list):
                out["servers"] = [{"value": s.get("uuid"), "label": s.get("name", s.get("uuid"))}
                                  for s in items if isinstance(s, dict)]
        except Exception as e:
            print(f"[remnawave] internal-squads: {e}")
        try:
            tags = await self._request("GET", "/api/users/tags")
            items = tags.get("tags") if isinstance(tags, dict) else tags
            if isinstance(items, list):
                out["plans"] = [{"value": str(t), "label": str(t)} for t in items]
        except Exception as e:
            print(f"[remnawave] users/tags: {e}")
        return out

    # ── Действия ──────────────────────────────────────────────────────────────

    async def ban(self, chat_id, reason=""):
        u = await self._first_user(chat_id)
        await self._request("POST", f"/api/users/{u['id']}/actions/disable")
        return ActionResult(ok=True, message=f"Клиент {u.get('username')} заблокирован")

    async def unban(self, chat_id):
        u = await self._first_user(chat_id)
        await self._request("POST", f"/api/users/{u['id']}/actions/enable")
        return ActionResult(ok=True, message=f"Клиент {u.get('username')} разблокирован")

    async def key_issue(self, chat_id, days=30, server="", plan=""):
        days = int(days or self.config.get("default_days", 30))
        expire = datetime.now(timezone.utc) + timedelta(days=days)
        payload = {
            # Имя должно быть уникальным в панели — собираем из Telegram ID и
            # метки времени, иначе повторная выдача упрётся в конфликт.
            "username": f"tg{chat_id}_{int(datetime.now(timezone.utc).timestamp())}",
            "telegramId": int(chat_id),
            "expireAt": expire.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        }
        squad = server or self.config.get("default_squad_uuid") or ""
        if squad:
            payload["activeInternalSquads"] = [squad]
        if plan:
            payload["tag"] = plan
        created = await self._request("POST", "/api/users", json=payload)
        name = created.get("username") if isinstance(created, dict) else payload["username"]
        return ActionResult(ok=True, message=f"Ключ {name} выдан на {days} дн.",
                            data={"subscriptionUrl": (created or {}).get("subscriptionUrl")})

    async def key_add_time(self, chat_id, key_id, days=0):
        days = int(days)
        if days == 0:
            return ActionResult(ok=False, message="Ноль дней — нечего менять")
        if days > 0:
            await self._request("POST", f"/api/users/{key_id}/actions/extend",
                                json={"days": days})
            return ActionResult(ok=True, message=f"Срок ключа продлён на {days} дн.")
        # extend умеет только прибавлять (days: minimum 1), поэтому убавление —
        # это чтение текущего срока и запись пересчитанного.
        user = await self._request("GET", f"/api/users/{key_id}")
        current = (user or {}).get("expireAt")
        if not current:
            return ActionResult(ok=False, message="У ключа не задан срок — нечего убавлять")
        base = datetime.fromisoformat(str(current).replace("Z", "+00:00"))
        new = base + timedelta(days=days)
        await self._request("PATCH", "/api/users", json={
            "id": int(key_id),
            "expireAt": new.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        })
        return ActionResult(ok=True,
                            message=f"Срок ключа убавлен на {abs(days)} дн. — до {_day(new.isoformat())}")

    async def key_replace(self, chat_id, key_id):
        data = await self._request("POST", f"/api/users/{key_id}/actions/revoke")
        return ActionResult(ok=True, message="Подписка перевыпущена, старая ссылка недействительна",
                            data={"subscriptionUrl": (data or {}).get("subscriptionUrl")})

    async def key_delete(self, chat_id, key_id):
        await self._request("DELETE", f"/api/users/{key_id}")
        return ActionResult(ok=True, message=f"Ключ {key_id} удалён")

    async def renew_subscription(self, chat_id, months=1):
        u = await self._first_user(chat_id)
        days = int(months) * 30
        await self._request("POST", f"/api/users/{u['id']}/actions/extend", json={"days": days})
        return ActionResult(ok=True, message=f"Подписка продлена на {months} мес. ({days} дн.)")

    async def buy_traffic(self, chat_id, gb=10):
        u = await self._first_user(chat_id)
        current = int(u.get("trafficLimitBytes") or 0)
        if current == 0:
            return ActionResult(ok=False, message="У клиента безлимитный тариф — докупать нечего")
        await self._request("PATCH", "/api/users", json={
            "id": int(u["id"]),
            "trafficLimitBytes": current + int(gb) * GB,
        })
        return ActionResult(ok=True, message=f"Добавлено {gb} ГБ трафика")

    async def reset_key(self, chat_id):
        u = await self._first_user(chat_id)
        await self._request("POST", f"/api/users/{u['id']}/actions/reset-traffic")
        return ActionResult(ok=True, message="Счётчик трафика сброшен")


register_customer_provider("remnawave", RemnawaveProvider)
