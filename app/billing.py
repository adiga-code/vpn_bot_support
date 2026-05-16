from abc import ABC, abstractmethod
from dataclasses import dataclass
import aiohttp


@dataclass
class BillingResult:
    ok: bool
    message: str = ""
    data: dict = None


class BillingProvider(ABC):
    """Базовый класс для биллинг-провайдеров. Подключи свой API — унаследуй и переопредели методы."""

    @abstractmethod
    async def renew_subscription(self, chat_id: str, dialog_id: str) -> BillingResult:
        """Продлить подписку пользователя."""

    @abstractmethod
    async def buy_traffic(self, chat_id: str, dialog_id: str) -> BillingResult:
        """Докупить трафик."""

    @abstractmethod
    async def reset_key(self, chat_id: str, dialog_id: str) -> BillingResult:
        """Сбросить VPN-ключ и выдать новый."""

    async def execute(self, action: str, chat_id: str, dialog_id: str) -> BillingResult:
        """Диспетчер: action = 'renew' | 'buy_traffic' | 'reset_key'."""
        handlers = {
            "renew":       self.renew_subscription,
            "buy_traffic": self.buy_traffic,
            "reset_key":   self.reset_key,
        }
        handler = handlers.get(action)
        if not handler:
            return BillingResult(ok=False, message=f"Unknown action: {action}")
        return await handler(chat_id, dialog_id)


# ── Заглушка для разработки / тестов ─────────────────────────────────────────

class StubBillingProvider(BillingProvider):
    """Ничего не делает, только логирует. Используй пока нет боевого API."""

    async def renew_subscription(self, chat_id: str, dialog_id: str) -> BillingResult:
        print(f"[STUB] renew_subscription chat_id={chat_id}")
        return BillingResult(ok=True, message="Stub: subscription renewed")

    async def buy_traffic(self, chat_id: str, dialog_id: str) -> BillingResult:
        print(f"[STUB] buy_traffic chat_id={chat_id}")
        return BillingResult(ok=True, message="Stub: traffic added")

    async def reset_key(self, chat_id: str, dialog_id: str) -> BillingResult:
        print(f"[STUB] reset_key chat_id={chat_id}")
        return BillingResult(ok=True, message="Stub: key reset")


# ── HTTP-провайдер (REST API твоего биллинга) ─────────────────────────────────

class HttpBillingProvider(BillingProvider):
    """
    Вызывает внешний REST API биллинговой системы.

    Настраивается через переменные окружения (см. config.py):
        BILLING_API_URL   — базовый URL, например https://billing.example.com/api
        BILLING_API_TOKEN — токен авторизации (Bearer)

    Формат запросов: POST /subscriptions/renew
                     POST /subscriptions/buy_traffic
                     POST /keys/reset
    Тело: { "chat_id": "...", "dialog_id": "..." }

    Чтобы подключить другой API — унаследуй HttpBillingProvider и переопредели
    нужные методы, или создай новый класс от BillingProvider.
    """

    def __init__(self, base_url: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

    async def _post(self, path: str, payload: dict) -> BillingResult:
        url = f"{self.base_url}{path}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=self.headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    body = await resp.json(content_type=None)
                    if resp.status < 300:
                        return BillingResult(ok=True, message=body.get("message", "OK"), data=body)
                    return BillingResult(ok=False, message=body.get("error") or body.get("message") or f"HTTP {resp.status}")
        except aiohttp.ClientError as e:
            return BillingResult(ok=False, message=f"Network error: {e}")
        except Exception as e:
            return BillingResult(ok=False, message=str(e))

    async def renew_subscription(self, chat_id: str, dialog_id: str) -> BillingResult:
        return await self._post("/subscriptions/renew", {"chat_id": chat_id, "dialog_id": dialog_id})

    async def buy_traffic(self, chat_id: str, dialog_id: str) -> BillingResult:
        return await self._post("/subscriptions/buy_traffic", {"chat_id": chat_id, "dialog_id": dialog_id})

    async def reset_key(self, chat_id: str, dialog_id: str) -> BillingResult:
        return await self._post("/keys/reset", {"chat_id": chat_id, "dialog_id": dialog_id})


# ── Фабрика: выбирает провайдер по конфигу ────────────────────────────────────

def make_billing_provider(billing_url: str, billing_token: str) -> BillingProvider:
    """
    Если BILLING_API_URL задан — возвращает HttpBillingProvider.
    Иначе — StubBillingProvider (безопасная заглушка).
    """
    if billing_url:
        return HttpBillingProvider(billing_url, billing_token)
    print("⚠️  BILLING_API_URL не задан — используется StubBillingProvider")
    return StubBillingProvider()
