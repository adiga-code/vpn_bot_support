"""Клиент вашей infra-API — основной источник состояния серверов и ботов.

Панель выступает потребителем: ходит в ваш сервис инфраструктуры и показывает
то, что он отдаёт. Ни Telegram, ни сами серверы напрямую не опрашиваются.

Регистрируется под двумя именами, потому что серверы и боты настраиваются
отдельно:

    infra       — серверы
    infra_bots  — боты

Конфиг (в пер-сервисной настройке `monitoring`, поле config):

    {
      "base_url":     "https://infra.example.com",
      "token":        "секрет",            # уходит как Bearer, см. auth_header
      "auth_header":  "Authorization",     # или "X-API-Key" — тогда без Bearer
      "servers_path": "/api/servers",
      "bots_path":    "/api/bots",
      "service_param": "service",          # чем фильтровать по ВПН-у
      "timeout": 10
    }

Ожидаемый ответ (массив либо объект с ключом items/data/servers/bots):

    {"items": [
      {"id": "fra-01", "name": "Frankfurt-01", "status": "ok",
       "location": "DE", "message": "",
       "metrics": {"load": 42.5, "ping": 12.3, "uptime": 99.9}}
    ]}

Если у вашей API другие имена полей — их не нужно подгонять на стороне
инфраструктуры, достаточно описать соответствие в конфиге:

    "mapping": {"id": "node_id", "name": "title", "status": "state",
                "location": "region"},
    "metrics_map": {"load": "cpu_pct", "ping": "rtt_ms", "uptime": "uptime_pct"},
    "status_map": {"online": "ok", "degraded": "high", "offline": "down"}
"""
import aiohttp

from app.health import BOTS, SERVERS, ComponentStatus, HealthProvider, register_provider
from app.redact import redact

# Как понимать статусы, которые пришли от вашей API. Слева — то, что может
# прислать инфраструктура, справа — наши четыре состояния.
_DEFAULT_STATUS_MAP = {
    "ok": "ok", "up": "ok", "online": "ok", "healthy": "ok", "running": "ok",
    "active": "ok", "true": "ok", "1": "ok",
    "high": "high", "degraded": "high", "warning": "high", "warn": "high",
    "overloaded": "high", "throttled": "high",
    "down": "down", "offline": "down", "failed": "down", "error": "down",
    "stopped": "down", "unhealthy": "down", "false": "down", "0": "down",
}

_DEFAULT_FIELDS = {"id": "id", "name": "name", "status": "status",
                   "location": "location", "message": "message"}


class _InfraProvider(HealthProvider):
    """Базовый клиент infra-API; отличие серверов и ботов — только в пути."""

    source = "infra"
    path_key = "servers_path"
    default_path = "/api/servers"
    list_keys = ("items", "data", "results", "servers", "bots", "nodes")

    async def check(self) -> list[ComponentStatus]:
        base = (self.config.get("base_url") or "").rstrip("/")
        if not base:
            return [self.make(
                f"{self.kind}-no-url", "infra-API не настроена", "unknown",
                message="Укажите base_url в настройке мониторинга сервиса",
            )]
        url = base + (self.config.get(self.path_key) or self.default_path)
        params = {}
        # По какому ВПН-у спрашиваем — инфраструктура общая на все сервисы.
        param = self.config.get("service_param", "service")
        if param:
            params[param] = self.service.get("slug", "")

        headers = {}
        token = self.config.get("token")
        if token:
            header = self.config.get("auth_header", "Authorization")
            headers[header] = f"Bearer {token}" if header.lower() == "authorization" else token

        timeout = aiohttp.ClientTimeout(total=float(self.config.get("timeout", 10)))
        try:
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.get(url, params=params, headers=headers) as r:
                    if r.status >= 400:
                        body = (await r.text())[:200]
                        return [self.make(f"{self.kind}-http", "infra-API вернула ошибку",
                                          "unknown", message=f"HTTP {r.status}: {body}")]
                    payload = await r.json(content_type=None)
        except Exception as e:
            return [self.make(f"{self.kind}-unreachable", "infra-API недоступна", "unknown",
                              message=redact(e)[:200])]

        items = self._extract(payload)
        if not items:
            return [self.make(f"{self.kind}-empty", "infra-API вернула пусто", "unknown",
                              message="В ответе нет ни одного компонента")]
        return [self._to_status(raw, i) for i, raw in enumerate(items)]

    def _extract(self, payload) -> list[dict]:
        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)]
        if isinstance(payload, dict):
            for key in self.list_keys:
                if isinstance(payload.get(key), list):
                    return [x for x in payload[key] if isinstance(x, dict)]
        return []

    def _to_status(self, raw: dict, idx: int) -> ComponentStatus:
        fields = {**_DEFAULT_FIELDS, **(self.config.get("mapping") or {})}
        get = lambda key, default="": raw.get(fields[key], default)  # noqa: E731

        status_map = {**_DEFAULT_STATUS_MAP,
                      **{str(k).lower(): v for k, v in (self.config.get("status_map") or {}).items()}}
        raw_status = get("status")
        status = status_map.get(str(raw_status).strip().lower(), "unknown")

        metrics_map = self.config.get("metrics_map") or {}
        if metrics_map:
            metrics = {ours: raw.get(theirs) for ours, theirs in metrics_map.items()
                       if raw.get(theirs) is not None}
        else:
            metrics = raw.get("metrics") if isinstance(raw.get("metrics"), dict) else {}
            metrics = dict(metrics or {})

        message = get("message") or ""
        if status == "unknown" and raw_status:
            # Статус пришёл, но мы его не знаем — покажем как есть, чтобы было
            # понятно, что дописать в status_map.
            message = message or f"неизвестный статус «{raw_status}»"

        return self.make(
            str(get("id") or f"{self.kind}-{idx}"),
            str(get("name") or get("id") or f"#{idx + 1}"),
            status,
            location=str(get("location") or ""),
            metrics=metrics,
            message=message,
        )


class InfraServersProvider(_InfraProvider):
    """Ваша infra-API: состояние VPN-серверов."""

    kind = SERVERS
    path_key = "servers_path"
    default_path = "/api/servers"


class InfraBotsProvider(_InfraProvider):
    """Ваша infra-API: состояние ботов."""

    kind = BOTS
    source = "infra"
    path_key = "bots_path"
    default_path = "/api/bots"


register_provider("infra", InfraServersProvider)
register_provider("infra_bots", InfraBotsProvider)
