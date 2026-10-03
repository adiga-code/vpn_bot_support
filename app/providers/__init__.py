"""Каталог для своих источников данных: мониторинг и карточка клиента.

Любой .py-файл отсюда импортируется автоматически при старте
(app.health.load_plugins). Чтобы подключить свою панель или API, положите сюда
модуль вида:

    from app.health import BOTS, SERVERS, ComponentStatus, HealthProvider, register_provider

    class MyPanelProvider(HealthProvider):
        \"\"\"Моя панель: состояние нод по HTTP API.\"\"\"
        kind, source = SERVERS, "mypanel"

        async def check(self) -> list[ComponentStatus]:
            data = await fetch(self.config["url"], self.config["token"])
            return [
                self.make(n["id"], n["name"], "ok" if n["alive"] else "down",
                          location=n.get("region", ""),
                          metrics={"load": n["cpu"], "ping": n["rtt"]})
                for n in data["nodes"]
            ]

    register_provider("mypanel", MyPanelProvider)

Дальше в панели: «Состояние» → блок «Источник данных» → выбрать mypanel.
Параметры (url, токен) кладутся в config настройки monitoring сервиса.
Ни один существующий файл приложения править не нужно.

Так же подключается источник данных о клиентах — профиль в карточке справа и
действия над аккаунтом (ключи, рефералы, бан, реф.баланс, сообщение в основного
бота). Реализовывать нужно только то, что умеет ваша API: панель показывает
кнопки лишь для переопределённых методов.

    from app.customer import (
        ActionResult, CustomerProfile, CustomerProvider, KeyInfo,
        register_customer_provider,
    )

    class MyCrmProvider(CustomerProvider):
        \"\"\"Моя CRM: профиль клиента и управление ключами.\"\"\"
        source = "mycrm"

        async def fetch(self, chat_id: str) -> CustomerProfile:
            u = await get(f"{self.config['url']}/users/{chat_id}")
            return CustomerProfile(
                tg_id=chat_id, username=u["nick"], plan=u["tariff"],
                ref_balance=u["ref_money"], ref_percent=u["ref_pct"],
                keys=[KeyInfo(id=k["id"], name=k["title"], server=k["node"],
                              expires_at=k["until"]) for k in u["keys"]],
            )

        async def options(self, chat_id: str) -> dict:
            return {"servers": [{"value": n, "label": n} for n in self.config["nodes"]]}

        async def key_issue(self, chat_id, days=30, server="", plan=""):
            await post(f"{self.config['url']}/keys", {"user": chat_id, "days": days})
            return ActionResult(ok=True, message=f"ключ на {days} дн. выдан")

    register_customer_provider("mycrm", MyCrmProvider)

Дальше: «Настройки» → «Клиенты» → выбрать mycrm. Список действий, каталог полей
и права (опасное — только админу) панель берёт из app/customer.py сама.
"""
