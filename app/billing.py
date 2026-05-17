from abc import ABC, abstractmethod
from dataclasses import dataclass

import aiohttp


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class BillingResult:
    ok: bool
    message: str = ""
    data: dict = None


# ── Base class ────────────────────────────────────────────────────────────────

class BillingProvider(ABC):

    @abstractmethod
    async def renew_subscription(self, chat_id: str, dialog_id: str) -> BillingResult: ...

    @abstractmethod
    async def buy_traffic(self, chat_id: str, dialog_id: str) -> BillingResult: ...

    @abstractmethod
    async def reset_key(self, chat_id: str, dialog_id: str) -> BillingResult: ...

    async def execute(self, action: str, chat_id: str, dialog_id: str) -> BillingResult:
        """Dispatch action string to the corresponding concrete method."""
        handlers = {
            "renew":       self.renew_subscription,
            "buy_traffic": self.buy_traffic,
            "reset_key":   self.reset_key,
        }
        handler = handlers.get(action)
        if not handler:
            return BillingResult(ok=False, message=f"Unknown action: {action}")
        return await handler(chat_id, dialog_id)


# ── Stub (development / testing) ──────────────────────────────────────────────

class StubBillingProvider(BillingProvider):
    """No-op implementation — logs calls and always returns success."""

    async def renew_subscription(self, chat_id: str, dialog_id: str) -> BillingResult:
        print(f"[STUB] renew_subscription chat_id={chat_id}")
        return BillingResult(ok=True, message="Stub: subscription renewed")

    async def buy_traffic(self, chat_id: str, dialog_id: str) -> BillingResult:
        print(f"[STUB] buy_traffic chat_id={chat_id}")
        return BillingResult(ok=True, message="Stub: traffic added")

    async def reset_key(self, chat_id: str, dialog_id: str) -> BillingResult:
        print(f"[STUB] reset_key chat_id={chat_id}")
        return BillingResult(ok=True, message="Stub: key reset")


# ── HTTP provider ─────────────────────────────────────────────────────────────

class HttpBillingProvider(BillingProvider):
    """
    Calls an external REST billing API.

    Configured via env vars (see config.py):
        BILLING_API_URL   — base URL, e.g. https://billing.example.com/api
        BILLING_API_TOKEN — Bearer token

    Endpoints called:
        POST /subscriptions/renew
        POST /subscriptions/buy_traffic
        POST /keys/reset
    Body: { "chat_id": "...", "dialog_id": "..." }

    To integrate a different API — subclass HttpBillingProvider and override
    the relevant methods, or create a new BillingProvider subclass from scratch.
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
                async with session.post(
                    url, json=payload, headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    body = await resp.json(content_type=None)
                    if resp.status < 300:
                        return BillingResult(ok=True, message=body.get("message", "OK"), data=body)
                    return BillingResult(
                        ok=False,
                        message=body.get("error") or body.get("message") or f"HTTP {resp.status}",
                    )
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


# ── Factory ───────────────────────────────────────────────────────────────────

def make_billing_provider(billing_url: str, billing_token: str) -> BillingProvider:
    """Return HttpBillingProvider when a URL is configured, otherwise StubBillingProvider."""
    if billing_url:
        return HttpBillingProvider(billing_url, billing_token)
    print("BILLING_API_URL not set — using StubBillingProvider")
    return StubBillingProvider()
