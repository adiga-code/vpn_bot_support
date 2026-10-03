"""Определение сервиса и диалога по входящему событию Telegram.

Единственное место, где решается «чей это ВПН и в какой тикет пишем». Им
пользуются обе точки входа: HTTP-ручка `/api/n8n/dialog/resolve`, которую
дёргает воркфлоу n8n, и потребитель RabbitMQ. Пока такой ответ вычислялся ещё
и на стороне n8n (нода «Определить сервис» + таблица `n8n_dialogs`), любое
расхождение двух реализаций рождало второй тикет на того же клиента.
"""

from app.database import DatabaseManager


async def resolve_service(db: DatabaseManager, data: dict) -> dict | None:
    """Сервис (ВПН) входящего события.

    Основной способ — `business_id`: Telegram присылает его с каждым сообщением
    из аккаунта поддержки, к которому подключён бот, и в панели он записан в
    карточке сервиса. Поэтому воркфлоу n8n один на всех и ничего про сервисы не
    знает.

    Дальше — `service` со слагом, как в старых воркфлоу; если нет и его, событие
    относится к первому (мигрированному) сервису. Неизвестный business_id или
    слаг — событие отбрасывается: свалить чужой тикет в первый попавшийся ВПН
    хуже, чем не принять его вовсе.
    """
    business_id = str(data.get("business_id")
                      or data.get("business_connection_id") or "").strip()
    if business_id:
        service = await db.get_service_by_business_id(business_id)
        if not service:
            print(f"[dialogs] неизвестный business_id '{business_id}' — "
                  f"событие отброшено; впишите его в карточку сервиса")
        return service

    slug = (data.get("service") or "").strip().lower()
    if not slug:
        services = await db.get_services()
        return services[0] if services else None
    service = await db.get_service_by_slug(slug)
    if not service:
        print(f"[dialogs] неизвестный сервис '{slug}' — событие отброшено")
    return service


def user_info_from(data: dict) -> dict:
    """Поля карточки клиента из события. Пустые значения не затирают уже
    известные — за это отвечает COALESCE в `resolve_open_dialog`."""
    return {k: data.get(k) for k in (
        "user_name", "user_username", "user_plan", "user_sub_status",
        "user_next_payment", "user_traffic_used", "user_traffic_total",
        "user_last_payment_amount", "user_last_payment_date",
        "user_photo_url",
    )}


def parse_ai_enabled(raw, default: bool = True) -> bool:
    """`ai_enabled` из события. n8n умеет прислать и строку — «false» и
    «inactive» должны означать выключенный ИИ, а не непустую строку."""
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() not in (
            "false", "0", "inactive", "disabled", "no", "off", "",
        )
    return bool(raw)
