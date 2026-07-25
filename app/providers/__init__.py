"""Каталог для своих источников данных мониторинга.

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
"""
