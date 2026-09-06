import asyncio
import json
import uuid
from pathlib import Path
from typing import Optional

from fastapi import Body, Depends, FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.ai_client import make_chat_client, make_kb_chat_client
from app.auth import create_token, decode_token, hash_password, verify_password
from app.config import Settings
from app.database import DatabaseManager, validate_slug as _validate_slug
from app.kb import delete_from_qdrant, process_document
from app.routing import AUTOMATION_DEFAULTS as _AUTOMATION_DEFAULTS, RoutingEngine
from app.serializers import (
    fmt_dialog as _fmt_dialog,
    fmt_message as _fmt_message,
    fmt_operator as _fmt_operator,
    fmt_time as _fmt_time,
)
from app.storage import make_storage
from app.summarizer import summarize_dialog
from app.n8n_client import N8NClient
from app.customer import (
    ACTIONS as _CUSTOMER_ACTIONS,
    ACTIONS_BY_NAME as _CUSTOMER_ACTIONS_BY_NAME,
    CUSTOMER_DEFAULTS,
    DANGEROUS as _CUSTOMER_DANGEROUS,
    CustomerService,
    build_customer_provider,
    known_customer_providers,
)
from app.health import MONITORING_DEFAULTS, ServiceHealthMonitor, known_providers
from app.providers.remnawave import check_connection as _remnawave_check_connection
from app.ws_manager import WebSocketManager

_STATIC = Path(__file__).parent / "static"

_AI_DEFAULTS = {
    "prompt": (
        "Ты — дружелюбный ассистент поддержки VPN-сервиса. "
        "Отвечай кратко, на русском. "
        "Если не знаешь ответ — предложи передать диалог оператору."
    ),
    "model": "gpt-4o-mini",
    "temperature": 0.7,
    "auto_reply": True,
    "handoff_enabled": True,
    "classification_enabled": False,
}

# The gate/handoff instruction is no longer concatenated onto the responder
# prompt. It is published to n8n as its own field
# (vpn_bot:ai_settings.handoff_prompt) that the gate node reads directly — see
# _sync_ai_settings_to_redis.


_SCHEDULE_DEFAULTS = {
    "mon": {"enabled": True,  "from": "09:00", "to": "21:00"},
    "tue": {"enabled": True,  "from": "09:00", "to": "21:00"},
    "wed": {"enabled": True,  "from": "09:00", "to": "21:00"},
    "thu": {"enabled": True,  "from": "09:00", "to": "21:00"},
    "fri": {"enabled": True,  "from": "09:00", "to": "21:00"},
    "sat": {"enabled": False, "from": "10:00", "to": "18:00"},
    "sun": {"enabled": False, "from": "10:00", "to": "18:00"},
}


# Formatters live in app.serializers; the _fmt_* aliases above are the names
# this module uses internally.


# ── Request bodies ────────────────────────────────────────────────────────────

class LoginBody(BaseModel):
    tg: str
    password: str

class SetupBody(BaseModel):
    name: str
    tg: str
    password: str

class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str

class ReplyBody(BaseModel):
    text: str = ""
    operator_name: str | None = None
    file_url: Optional[str] = None
    file_type: Optional[str] = None

class CommentBody(BaseModel):
    text: str

class HandoffBody(BaseModel):
    operator_name: str | None = None

class OperatorBody(BaseModel):
    name: str
    tg: str
    tg_id: Optional[int] = None
    role: str = "agent"
    password: str = ""
    # Флаги доступа к ВПН-ам при создании; правятся через
    # PUT /api/operators/{id}/services.
    service_ids: list[int] = []

class AISettingsBody(BaseModel):
    prompt: str
    model: str = "gpt-4o-mini"
    temperature: float
    auto_reply: bool
    handoff_enabled: bool
    classification_enabled: bool = False

class NotifPrefsBody(BaseModel):
    new_dialog:      bool = True
    operator_called: bool = True
    server_down:     bool = True
    sound_enabled:   bool = True

class ScheduleBody(BaseModel):
    schedule: dict

class AutomationSettingsBody(BaseModel):
    operator_button_enabled: bool = False
    operator_button_after_msgs: int = 3
    auto_handoff_enabled: bool = False
    rating_enabled: bool = False
    rating_message_text: str = "Оцените качество поддержки:"
    rating_thanks_text: str = "Спасибо за оценку! 🙏"
    close_message_enabled: bool = False
    close_message_text: str = ""
    max_tickets_per_operator: int = 10
    offline_grace_seconds: int = 60
    operator_call_keywords: str = "оператор, менеджер, жив человек, реальн человек, поддержк"
    handoff_instruction_text: str = _AUTOMATION_DEFAULTS["handoff_instruction_text"]

class BroadcastBody(BaseModel):
    text: str

class TemplateBody(BaseModel):
    group_name: str = "Общие"
    title: str
    text: str

class TransferBody(BaseModel):
    operator_name: str

class PauseBody(BaseModel):
    paused: bool

class RenameGroupBody(BaseModel):
    old_name: str
    new_name: str

class NotesBody(BaseModel):
    text: str

class PhotoBody(BaseModel):
    url: str

class ServiceBody(BaseModel):
    # slug задаётся только при создании: он зашивается в воркфлоу n8n, ключи
    # Redis, имя коллекции Qdrant и префикс dialog_id — менять его задним
    # числом небезопасно.
    slug: str = ""
    name: str
    color: str = "#4F8EF7"
    emoji: Optional[str] = None
    n8n_webhook_url: str = ""
    is_active: bool = True
    # business_connection_id аккаунта поддержки: по нему панель узнаёт свой
    # сервис во входящем сообщении, поэтому воркфлоу n8n один на всех.
    business_id: str = ""
    # Support API этого ВПН-а. Заполняются в той же форме, что и сам сервис, и
    # сохраняются в настройку `customer` — отдельный экран для этого не нужен.
    # Пустой api_token при правке означает «оставить прежний».
    api_base_url: str = ""
    api_token: str = ""
    # Remnawave: только статистика серверов (monitoring.servers), с
    # источником данных о клиенте не связано — см. _save_service_remnawave.
    # Пустые remnawave_token/remnawave_cookie при правке — «оставить прежние».
    remnawave_base_url: str = ""
    remnawave_token: str = ""
    # Нужен, только если панель за прокси/WAF, требующим статическую куку.
    remnawave_cookie: str = ""


class ApiCheckBody(BaseModel):
    base_url: str = ""
    token: str = ""
    # Нужен только для remnawave за прокси/WAF, требующим статическую куку.
    cookie: str = ""
    # bot_api — Support API этого ВПН-а, remnawave — панель Remnawave.
    provider: str = "bot_api"
    # Правка сохранённого сервиса: форма шлёт пустой токен, когда менять его не
    # собираются, и проверка должна взять сохранённый — иначе она уходит с
    # пустым Bearer и рисует «Связи нет» на исправном сервисе.
    service_id: Optional[int] = None

class FolderBody(BaseModel):
    """Папка-ярлык: имя и эмодзи задаёт админ, цвет — из той же палитры, что
    у сервисов."""
    name: str
    emoji: str = "📁"
    color: str = "#4F8EF7"
    sort_order: Optional[int] = None


class DialogFolderBody(BaseModel):
    # null — вынуть тикет из папки
    folder_id: Optional[int] = None


class FallbackAuthBody(BaseModel):
    """Шаг 1 авторизации резервного аккаунта: реквизиты приложения с
    my.telegram.org и телефон аккаунта поддержки."""
    app_id: int
    app_hash: str
    phone: str


class FallbackCodeBody(BaseModel):
    """Шаг 2: код из Телеграм и, если он стоит, пароль двухфакторки."""
    code: str = ""
    password: str = ""


class FallbackSessionBody(BaseModel):
    """Готовая строка сессии, сгенерированная снаружи — вместо шагов с кодом."""
    app_id: int
    app_hash: str
    phone: str = ""
    session: str


class FallbackToggleBody(BaseModel):
    enabled: bool


class OperatorServicesBody(BaseModel):
    service_ids: list[int] = []

class MonitoringSourceBody(BaseModel):
    provider: str
    config: dict = {}

class MonitoringBody(BaseModel):
    """Пер-сервисный мониторинг: какой источник данных опрашивать по серверам и
    по ботам. Имена провайдеров — из реестра app.health."""
    interval: int = 300
    servers: MonitoringSourceBody
    bots: MonitoringSourceBody


class CustomerBody(BaseModel):
    """Пер-сервисный источник данных о клиентах. Имя провайдера — из реестра
    app.customer; config целиком отдаётся провайдеру, его форму знает только он."""
    provider: str = "mock"
    config: dict = {}
    cacheTtl: int = 60


# ── App factory ───────────────────────────────────────────────────────────────

def build_app(
    settings: Settings,
    db: DatabaseManager,
    ws: WebSocketManager,
    n8n: N8NClient,
    routing: RoutingEngine,
    customers: CustomerService,
    health: ServiceHealthMonitor,
    fallback=None,
) -> FastAPI:
    app = FastAPI(title="VPN Helpdesk")
    uploads = settings.uploads_path()
    chat_client = make_chat_client(settings.CHAT_PROVIDER, settings.OPENAI_API_KEY, settings.GEMINI_API_KEY)
    kb_chat_client = make_kb_chat_client(settings.CHAT_PROVIDER, settings.OPENAI_API_KEY, settings.GEMINI_API_KEY)
    storage = make_storage(settings)

    if _STATIC.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

    @app.middleware("http")
    async def strip_root_prefix(request: Request, call_next):
        # When nginx proxies without stripping the subpath prefix (e.g. /files/),
        # rewrite the path so routes match correctly.
        path = request.scope["path"]
        root = settings.BASE_URL_PATH
        if root and path.startswith(root + "/"):
            request.scope["path"] = path[len(root):]
            if "raw_path" in request.scope:
                request.scope["raw_path"] = request.scope["raw_path"][len(root):]
        return await call_next(request)

    @app.middleware("http")
    async def no_cache_static(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.endswith((".jsx", ".js", ".html")):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response

    # Auth dependency — defined here for closure access to db and settings
    async def require_auth(authorization: Optional[str] = Depends(
        lambda authorization: authorization  # FastAPI Header injection below
    )) -> dict:
        raise NotImplementedError  # replaced below

    # Proper Header-based dependency
    from fastapi import Header

    async def require_auth(authorization: Optional[str] = Header(None)) -> dict:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "Not authenticated")
        op_id = decode_token(authorization[7:], settings.SECRET_KEY)
        if not op_id:
            raise HTTPException(401, "Invalid or expired token")
        op = await db.get_operator(op_id)
        if not op:
            raise HTTPException(401, "Operator not found")
        return op

    # ── Доступ к сервисам ─────────────────────────────────────────────────────
    # Оператор работает только с теми ВПН-сервисами, на которые ему выдан флаг
    # (админ — со всеми). Каждый запрос по диалогу проходит через
    # require_dialog, каждый настроечный — через require_service.

    async def require_service(service_id: Optional[int], operator: dict) -> dict:
        """Сервис из query-параметра с проверкой доступа. Без параметра —
        первый доступный: настройкам и рассылке всегда нужен конкретный ВПН."""
        ids = await db.get_operator_service_ids(operator)
        if not ids:
            raise HTTPException(403, "Оператору не назначен ни один сервис")
        target = ids[0] if service_id is None else service_id
        if target not in ids:
            raise HTTPException(403, "Нет доступа к этому сервису")
        service = await db.get_service(target)
        if not service:
            raise HTTPException(404, "Сервис не найден")
        return service

    async def require_dialog(dialog_id: str, operator: dict) -> dict:
        dialog = await db.get_dialog(dialog_id)
        if not dialog:
            raise HTTPException(404)
        if dialog["service_id"] not in await db.get_operator_service_ids(operator):
            raise HTTPException(403, "Нет доступа к этому сервису")
        return dialog

    async def require_dialog_write(dialog_id: str, operator: dict) -> dict:
        """То же плюс владение: пока тикет в работе у одного оператора, второй
        такого же уровня его только читает — двое, пишущих клиенту разное, хуже
        любой задержки с ответом. Забрать тикет он может кнопкой «Запросить»:
        владелец передаёт его сам.

        Админ не ограничен — иначе разруливать зависшие тикеты было бы некому.
        Комментарии и заметки под этот гард не попадают: ради них второй
        оператор в чужой тикет и заходит.

        423 Locked, а не 403: «тикет занят» и «нет доступа к сервису» — разные
        вещи, и фронт должен уметь их различить."""
        dialog = await require_dialog(dialog_id, operator)
        owner = dialog.get("assigned_operator")
        if (operator["role"] != "admin" and owner and owner != operator["name"]
                and dialog["status"] in ("in_progress", "waiting")):
            raise HTTPException(423, f"Тикет в работе у оператора {owner}")
        return dialog

    # ── Static / index ────────────────────────────────────────────────────────

    @app.get("/")
    async def index():
        return FileResponse(_STATIC / "index.html")

    @app.get("/api/files/{filename}")
    async def serve_file(filename: str):
        path = uploads / filename
        if not path.exists():
            raise HTTPException(404, "File not found")
        return FileResponse(path)

    # ── Auth (public) ─────────────────────────────────────────────────────────

    @app.get("/api/auth/status")
    async def auth_status():
        """Returns whether first-time setup is needed (no operators in DB)."""
        count = await db.pool.fetchval("SELECT COUNT(*) FROM operators")
        return {"setup_needed": count == 0}

    @app.post("/api/auth/setup")
    async def setup(body: SetupBody):
        """Create the first admin account. Fails if any operator already exists."""
        count = await db.pool.fetchval("SELECT COUNT(*) FROM operators")
        if count > 0:
            raise HTTPException(403, "Setup already completed")
        if len(body.password) < 6:
            raise HTTPException(400, "Password must be at least 6 characters")
        op = await db.create_operator(body.name, body.tg, "admin")
        await db.set_password(op["id"], hash_password(body.password))
        token = create_token(op["id"], settings.SECRET_KEY)
        return {"token": token, "operator": _fmt_operator(op)}

    @app.post("/api/auth/login")
    async def login(body: LoginBody):
        op = await db.get_operator_by_tg(body.tg)
        if not op or not op.get("password_hash"):
            raise HTTPException(401, "Неверный логин или пароль")
        if not verify_password(body.password, op["password_hash"]):
            raise HTTPException(401, "Неверный логин или пароль")
        token = create_token(op["id"], settings.SECRET_KEY)
        return {"token": token, "operator": _fmt_operator(op)}

    # ── Auth (protected) ──────────────────────────────────────────────────────

    @app.get("/api/auth/me")
    async def me(operator: dict = Depends(require_auth)):
        return _fmt_operator(operator)

    @app.post("/api/auth/logout")
    async def logout(operator: dict = Depends(require_auth)):
        # JWT is stateless — client drops the token
        return {"ok": True}

    @app.put("/api/auth/password")
    async def change_password(body: ChangePasswordBody, operator: dict = Depends(require_auth)):
        if not operator.get("password_hash"):
            raise HTTPException(400, "No password set")
        if not verify_password(body.current_password, operator["password_hash"]):
            raise HTTPException(400, "Неверный текущий пароль")
        if len(body.new_password) < 6:
            raise HTTPException(400, "Password must be at least 6 characters")
        await db.set_password(operator["id"], hash_password(body.new_password))
        return {"ok": True}

    # ── Dialogs ───────────────────────────────────────────────────────────────

    @app.get("/api/dialogs")
    async def get_dialogs(service_id: Optional[int] = None, operator: dict = Depends(require_auth)):
        """С service_id — один сервис; без него — все доступные оператору
        (режим «Все сервисы» в переключателе)."""
        ids = await db.get_operator_service_ids(operator)
        if service_id is not None:
            if service_id not in ids:
                raise HTTPException(403, "Нет доступа к этому сервису")
            ids = [service_id]
        rows = await db.get_all_dialogs(ids)
        return [_fmt_dialog(r) for r in rows]

    @app.get("/api/dialogs/{dialog_id}")
    async def get_dialog(dialog_id: str, operator: dict = Depends(require_auth)):
        row = await require_dialog(dialog_id, operator)
        tickets = await db.get_dialog_history(row["service_id"], row["chat_id"], dialog_id)
        return _fmt_dialog(row, [
            {
                "id": f"T-{t['dialog_id'][-4:]}",
                "dialogId": t["dialog_id"],
                "title": t.get("summary") or t["last_message_text"] or "Диалог",
                "date": _fmt_time(t["updated_at"]),
                "solved": True,
                "rating": t.get("rating"),
            }
            for t in tickets
        ])

    @app.get("/api/dialogs/{dialog_id}/history")
    async def get_dialog_history(dialog_id: str, operator: dict = Depends(require_auth)):
        row = await require_dialog(dialog_id, operator)
        history = await db.get_dialog_history(row["service_id"], row["chat_id"], dialog_id)
        return [
            {
                "id": f"T-{t['dialog_id'][-4:]}",
                "dialogId": t["dialog_id"],
                "title": t.get("summary") or t["last_message_text"] or "Диалог",
                "date": _fmt_time(t["updated_at"]),
                "solved": True,
            }
            for t in history
        ]

    @app.get("/api/dialogs/{dialog_id}/messages")
    async def get_messages(dialog_id: str, operator: dict = Depends(require_auth)):
        await require_dialog(dialog_id, operator)
        await db.clear_unread(dialog_id)
        rows = await db.get_messages(dialog_id)
        await routing.emit_counts()
        return [_fmt_message(r) for r in rows]

    @app.post("/api/dialogs/{dialog_id}/reply")
    async def reply(dialog_id: str, body: ReplyBody, operator: dict = Depends(require_auth)):
        dialog = await require_dialog_write(dialog_id, operator)

        op_name = body.operator_name or operator["name"] or "Оператор"
        msg_row = await db.save_message(
            dialog_id, "operator",
            body.text or None,
            file_type=body.file_type,
            file_url=body.file_url,
            operator_name=op_name,
        )
        preview = body.text or (f"[{body.file_type}]" if body.file_type else "—")
        await db.update_last_message(dialog_id, preview)

        delivered = await n8n.send_manager_message(
            dialog_id, dialog["chat_id"], body.text,
            file_url=body.file_url, file_type=body.file_type,
            message_id=msg_row["id"], service=dialog,
        )
        if not delivered:
            # До n8n сообщение не доехало вовсе — пробуем резервный канал сразу,
            # подтверждения доставки ждать неоткуда.
            status, error = "failed", "Очередь недоступна"
            if fallback:
                ok, detail = await fallback.send(
                    dialog["service_id"], dialog["chat_id"], body.text, body.file_url)
                if detail:
                    note = ("Очередь недоступна — " +
                            (detail if ok else f"резервная отправка тоже не удалась: {detail}"))
                    sys_row = await db.save_message(dialog_id, "system", note)
                    await ws.broadcast({"type": "new_message", "dialog_id": dialog_id,
                                        "message": _fmt_message(sys_row)}, dialog["service_id"])
                    if ok:
                        status, delivered = "delivered_fallback", True
                    else:
                        error = f"Очередь недоступна · резерв: {detail}"
            await db.update_message_delivery(msg_row["id"], status, error)
        await db.clear_unread(dialog_id)

        await ws.broadcast({"type": "new_message", "dialog_id": dialog_id,
                            "message": _fmt_message(msg_row)}, dialog["service_id"])
        # Scenario 2: the answered ticket moves to waiting («ждём ответ»),
        # SLA pauses, the slot frees up (broadcasts the updated dialog).
        await routing.on_operator_reply(dialog, op_name)
        return {"ok": True, "delivered": delivered}

    @app.post("/api/dialogs/{dialog_id}/comment")
    async def add_comment(dialog_id: str, body: CommentBody, operator: dict = Depends(require_auth)):
        dialog = await require_dialog(dialog_id, operator)
        if not body.text.strip():
            raise HTTPException(400, "Пустой комментарий")
        msg_row = await db.save_message(
            dialog_id, "comment", body.text.strip(), operator_name=operator["name"]
        )
        await ws.broadcast({"type": "new_message", "dialog_id": dialog_id,
                            "message": _fmt_message(msg_row)}, dialog["service_id"])
        return {"ok": True}

    @app.put("/api/dialogs/{dialog_id}/notes")
    async def update_notes(dialog_id: str, body: NotesBody, operator: dict = Depends(require_auth)):
        await require_dialog(dialog_id, operator)
        await db.pool.execute(
            "UPDATE dialogs SET user_notes=$1 WHERE dialog_id=$2", body.text, dialog_id
        )
        updated = await db.get_dialog(dialog_id)
        await ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)},
                           updated["service_id"])
        return {"ok": True}

    @app.post("/api/dialogs/{dialog_id}/dismiss_called")
    async def dismiss_called(dialog_id: str, operator: dict = Depends(require_auth)):
        await require_dialog_write(dialog_id, operator)
        await db.pool.execute(
            "UPDATE dialogs SET operator_called=FALSE WHERE dialog_id=$1", dialog_id
        )
        updated = await db.get_dialog(dialog_id)
        await ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)},
                           updated["service_id"])
        return {"ok": True}

    @app.get("/api/dialogs/{dialog_id}/has_photo")
    async def has_photo(dialog_id: str, request: Request):
        key = request.headers.get("X-API-Key", "")
        if not settings.N8N_API_KEY or key != settings.N8N_API_KEY:
            raise HTTPException(401, "Invalid API key")
        row = await db.pool.fetchrow(
            "SELECT user_photo_url FROM dialogs WHERE dialog_id=$1", dialog_id
        )
        return {"has_photo": bool(row and row["user_photo_url"])}

    @app.post("/api/dialogs/{dialog_id}/set_photo")
    async def set_photo(dialog_id: str, request: Request, body: PhotoBody):
        key = request.headers.get("X-API-Key", "")
        if not settings.N8N_API_KEY or key != settings.N8N_API_KEY:
            raise HTTPException(401, "Invalid API key")
        await db.pool.execute(
            "UPDATE dialogs SET user_photo_url=$1 WHERE dialog_id=$2", body.url, dialog_id
        )
        updated = await db.get_dialog(dialog_id)
        if updated:
            await ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)},
                               updated["service_id"])
        return {"ok": True}

    @app.post("/api/dialogs/{dialog_id}/toggle_ai")
    async def toggle_ai(dialog_id: str, operator: dict = Depends(require_auth)):
        dialog = await require_dialog_write(dialog_id, operator)
        new_value = not dialog["ai_enabled"]
        await db.update_ai_enabled(dialog_id, new_value)
        await db.sync_n8n_dialog_ai_status(dialog["chat_id"], new_value, dialog)
        await n8n.notify_ai_toggled(dialog_id, dialog["chat_id"], new_value, dialog)
        # Keep the status model coherent: AI back on while queued → «ИИ» section;
        # AI off while unattended in «ИИ» → escalate to humans.
        await routing.on_ai_toggled(dialog_id, new_value)
        updated = await db.get_dialog(dialog_id)
        await ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)},
                           updated["service_id"])
        return {"ai_enabled": new_value}

    @app.post("/api/dialogs/{dialog_id}/handoff")
    async def handoff(dialog_id: str, body: HandoffBody = HandoffBody(), operator: dict = Depends(require_auth)):
        await require_dialog_write(dialog_id, operator)
        op_name = body.operator_name or operator["name"] or "Оператор"
        updated = await routing.take_in_work(dialog_id, op_name)
        if not updated:
            raise HTTPException(400, "Dialog is closed")
        return {"ok": True}

    @app.post("/api/dialogs/{dialog_id}/reopen-closed")
    async def reopen_closed_dialog(dialog_id: str, operator: dict = Depends(require_auth)):
        dialog = await require_dialog_write(dialog_id, operator)
        if dialog["status"] != "closed":
            raise HTTPException(400, "Dialog is not closed")
        active = await db.get_active_dialog_by_chat_id(
            dialog["service_id"], dialog["chat_id"], exclude_dialog_id=dialog_id
        )
        if active:
            return JSONResponse(status_code=409, content={"active_dialog_id": active["dialog_id"]})
        # → queue, unassigned; AI stays off (the ticket had been escalated)
        await routing.reopen_closed(dialog_id, dialog["chat_id"])
        return {"ok": True}

    @app.post("/api/dialogs/{dialog_id}/reopen")
    async def reopen_dialog(dialog_id: str, operator: dict = Depends(require_auth)):
        dialog = await require_dialog_write(dialog_id, operator)
        if dialog["status"] == "closed":
            raise HTTPException(400, "Cannot reopen closed dialog")
        # → queue for another operator; the AI is NOT re-enabled — the ticket
        # was already escalated (use the AI toggle to hand it back to the bot).
        await routing.return_to_queue(dialog_id)
        return {"ok": True}

    @app.post("/api/dialogs/{dialog_id}/wait")
    async def wait_dialog(dialog_id: str, operator: dict = Depends(require_auth)):
        """Manual «В ожидание»: pause an in_progress ticket (red label
        «клиент ждёт ответ») while the operator waits for the team."""
        await require_dialog_write(dialog_id, operator)
        try:
            await routing.set_waiting_manual(dialog_id, operator["name"])
        except ValueError:
            raise HTTPException(400, "Only in_progress tickets can be paused")
        return {"ok": True}

    @app.post("/api/dialogs/{dialog_id}/transfer")
    async def transfer_dialog(dialog_id: str, body: TransferBody, operator: dict = Depends(require_auth)):
        dialog = await require_dialog_write(dialog_id, operator)
        if operator["role"] != "admin" and dialog.get("assigned_operator") != operator["name"]:
            raise HTTPException(403, "Can only transfer your own dialogs")
        target = await db.get_operator_by_name(body.operator_name)
        if not target:
            raise HTTPException(404, "Target operator not found")
        # Передать тикет можно только тому, у кого есть доступ к этому сервису.
        if dialog["service_id"] not in await db.get_operator_service_ids(target):
            raise HTTPException(400, "У оператора нет доступа к сервису этого тикета")
        await routing.transfer(dialog_id, body.operator_name)
        return {"ok": True}

    # ── Запрос на передачу тикета ─────────────────────────────────────────────
    # Пока тикет в работе у одного оператора, второй его только читает
    # (require_dialog_write). Забрать тикет он может, попросив владельца:
    # тот жмёт «Передать» и тикет переходит штатным transfer-ом.

    async def _claim_state(dialog_id: str) -> dict:
        """Свежий диалог + рассылка обновления тем, кто его видит."""
        updated = await db.get_dialog(dialog_id)
        await ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)},
                           updated["service_id"])
        return updated

    @app.post("/api/dialogs/{dialog_id}/claim")
    async def claim_dialog(dialog_id: str, operator: dict = Depends(require_auth)):
        """«Запросить»: второй оператор просит владельца отдать ему тикет."""
        dialog = await require_dialog(dialog_id, operator)
        owner = dialog.get("assigned_operator")
        if not owner or dialog["status"] not in ("in_progress", "waiting"):
            raise HTTPException(400, "Этот тикет ни за кем не закреплён — берите его в работу")
        if owner == operator["name"]:
            raise HTTPException(400, "Тикет уже ваш")
        if dialog.get("claim_requested_by") == operator["name"]:
            return {"ok": True, "detail": "Запрос уже отправлен"}
        await db.set_claim_request(dialog_id, operator["name"])
        msg_row = await db.save_message(
            dialog_id, "system", f"{operator['name']} просит передать тикет")
        await ws.broadcast({"type": "new_message", "dialog_id": dialog_id,
                            "message": _fmt_message(msg_row)}, dialog["service_id"])
        await _claim_state(dialog_id)
        # Точечно владельцу — чтобы просьба не потерялась среди чужих событий.
        owner_row = await db.get_operator_by_name(owner)
        if owner_row:
            await ws.send_to_operator(owner_row["id"], {
                "type": "claim_requested", "dialog_id": dialog_id,
                "by": operator["name"], "client": dialog.get("user_name") or dialog_id,
            })
        # И в Телеграм — владелец может быть не за панелью.
        await n8n.schedule_notify("claim_requested", {
            "dialog_id": dialog_id, "operator_name": operator["name"],
            "owner_name": owner, "username": dialog.get("user_username") or dialog_id,
        }, dialog)
        return {"ok": True}

    async def _require_claim_owner(dialog_id: str, operator: dict) -> dict:
        """Отвечать на запрос вправе владелец тикета и админ."""
        dialog = await require_dialog(dialog_id, operator)
        if not dialog.get("claim_requested_by"):
            raise HTTPException(400, "По этому тикету запроса нет")
        if (operator["role"] != "admin"
                and dialog.get("assigned_operator") != operator["name"]):
            raise HTTPException(403, "Ответить на запрос может только владелец тикета")
        return dialog

    @app.post("/api/dialogs/{dialog_id}/claim/approve")
    async def approve_claim(dialog_id: str, operator: dict = Depends(require_auth)):
        dialog = await _require_claim_owner(dialog_id, operator)
        target_name = dialog["claim_requested_by"]
        target = await db.get_operator_by_name(target_name)
        if not target:
            await db.set_claim_request(dialog_id, None)
            raise HTTPException(404, "Просивший оператор больше не существует")
        if dialog["service_id"] not in await db.get_operator_service_ids(target):
            await db.set_claim_request(dialog_id, None)
            raise HTTPException(400, "У оператора нет доступа к сервису этого тикета")
        # transfer сам снимет запрос (set_assigned_operator / move_to_in_progress).
        await routing.transfer(dialog_id, target_name)
        return {"ok": True, "operator_name": target_name}

    @app.post("/api/dialogs/{dialog_id}/claim/decline")
    async def decline_claim(dialog_id: str, operator: dict = Depends(require_auth)):
        dialog = await _require_claim_owner(dialog_id, operator)
        who = dialog["claim_requested_by"]
        await db.set_claim_request(dialog_id, None)
        msg_row = await db.save_message(
            dialog_id, "system", f"{operator['name']} оставил тикет за собой (запрос {who} отклонён)")
        await ws.broadcast({"type": "new_message", "dialog_id": dialog_id,
                            "message": _fmt_message(msg_row)}, dialog["service_id"])
        await _claim_state(dialog_id)
        return {"ok": True}

    @app.post("/api/dialogs/{dialog_id}/close")
    async def close_dialog(dialog_id: str, operator: dict = Depends(require_auth)):
        dialog = await require_dialog_write(dialog_id, operator)
        # Transition + system message + broadcasts + n8n sync + queue drain
        await routing.close(dialog_id, dialog["chat_id"], operator["name"])
        if chat_client:
            asyncio.create_task(_summarize_dialog_bg(dialog_id))
        automation = await db.get_setting_json(
            "automation", _AUTOMATION_DEFAULTS, dialog["service_id"]
        )
        if automation.get("close_message_enabled") and automation.get("close_message_text"):
            asyncio.create_task(
                n8n.send_to_user(dialog["chat_id"], automation["close_message_text"], service=dialog)
            )
        if automation.get("rating_enabled"):
            rating_text = automation.get("rating_message_text") or "Оцените качество поддержки:"
            asyncio.create_task(
                n8n.send_rating_request(dialog["chat_id"], dialog_id, rating_text, service=dialog)
            )
        return {"ok": True}

    async def _summarize_dialog_bg(dialog_id: str):
        try:
            messages = await db.get_messages_for_summary(dialog_id)
            summary = await summarize_dialog(messages, chat_client)
            if summary:
                await db.save_dialog_summary(dialog_id, summary)
                print(f"[summarizer] dialog={dialog_id} → {summary}")
        except Exception as e:
            print(f"[summarizer] bg error: {e}")

    # ── Карточка клиента ──────────────────────────────────────────────────────
    # Профиль и управление аккаунтом живут во внешней API; панель знает только
    # канонический вид (app/customer.py) и никогда не падает из-за чужого
    # сервиса — при недоступности отдаётся снапшот с пометкой stale.

    @app.get("/api/dialogs/{dialog_id}/customer")
    async def get_customer(dialog_id: str, refresh: bool = False,
                           operator: dict = Depends(require_auth)):
        dialog = await require_dialog(dialog_id, operator)
        service = await db.get_service(dialog["service_id"])
        profile = await customers.profile(service, dialog, refresh=refresh)
        supported = set(await customers.supports(service))
        is_admin = operator["role"] == "admin"
        # Кнопку, которой нет у источника или прав, панель просто не рисует.
        actions = [a.to_dict() for a in _CUSTOMER_ACTIONS
                   if a.name in supported and (is_admin or not a.danger)]
        return {**profile.to_dict(), "actions": actions,
                "options": await customers.options(service, dialog)}

    @app.post("/api/dialogs/{dialog_id}/customer/{action}")
    async def customer_action(dialog_id: str, action: str, body: dict = Body(default={}),
                              operator: dict = Depends(require_auth)):
        spec = _CUSTOMER_ACTIONS_BY_NAME.get(action)
        if not spec:
            raise HTTPException(400, f"Неизвестное действие: {action}")
        if action in _CUSTOMER_DANGEROUS and operator["role"] != "admin":
            raise HTTPException(403, "Действие доступно только администратору")
        dialog = await require_dialog_write(dialog_id, operator)
        service = await db.get_service(dialog["service_id"])
        result = await customers.execute(service, dialog, action, body or {},
                                         operator=operator["name"])
        if not result.ok:
            raise HTTPException(502, result.message)
        # След в переписке: кто и что сделал с аккаунтом клиента. Отдельная
        # таблица не нужна — история тикета и есть журнал.
        msg_row = await db.save_message(
            dialog_id, "system",
            f"{operator['name']}: {result.message or spec.label}",
        )
        if msg_row:
            await ws.broadcast({"type": "new_message", "dialog_id": dialog_id,
                                "message": _fmt_message(msg_row)}, dialog["service_id"])
        return {"ok": True, "message": result.message, "data": result.data or {}}

    @app.get("/api/dialogs/{dialog_id}/activity")
    async def get_customer_activity(dialog_id: str, limit: int = 100,
                                    operator: dict = Depends(require_auth)):
        """Лента «Действия»: всё, что происходило с аккаунтом клиента — оплаты и
        пополнения, продления и сбросы ключей, баны, изменения баланса, — и то,
        что делали операторы из самой панели.

        Внешний источник и наша БД собираются в один список по времени. Отчёт об
        источниках уходит рядом: если журнал бота закрыт скоупом токена, оператор
        должен видеть, чего он НЕ видит, а не решить, что ничего не было."""
        dialog = await require_dialog(dialog_id, operator)
        service = await db.get_service(dialog["service_id"])
        events, sources = await customers.activity(service, dialog, limit)
        items = [e.to_dict() for e in events]

        for row in await db.get_customer_activity(dialog["service_id"], dialog["chat_id"], limit):
            text = row.get("text") or ""
            # Строка записана как «Оператор: что сделал» — имя слева от первого
            # двоеточия, по этому же признаку она и отобрана в запросе.
            actor, _, rest = text.partition(": ")
            items.append({
                "at": row["created_at"].isoformat() if row.get("created_at") else "",
                "kind": "panel", "title": rest or text, "detail": "",
                "actor": actor if rest else "", "amount": None, "currency": "₽",
                "source": "панель",
            })
        sources.append({"name": "панель", "ok": True, "error": ""})

        items.sort(key=lambda e: e.get("at") or "", reverse=True)
        return {"items": items[:limit], "sources": sources}

    @app.get("/api/settings/customer")
    async def get_customer_settings(service_id: Optional[int] = None,
                                    operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        service = await require_service(service_id, operator)
        stored = await db.get_setting_json("customer", None, service["id"]) or {}
        return {**CUSTOMER_DEFAULTS, **stored,
                "serviceId": service["id"], "serviceName": service["name"],
                # Реестр источников — админка строит выбор по нему, поэтому свой
                # провайдер появляется в UI сам собой.
                "available": known_customer_providers(),
                "catalog": [a.to_dict() for a in _CUSTOMER_ACTIONS]}

    @app.put("/api/settings/customer")
    async def save_customer_settings(body: CustomerBody, service_id: Optional[int] = None,
                                     operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        service = await require_service(service_id, operator)
        await db.set_setting_json("customer", body.model_dump(), service["id"])
        # Пересоздать провайдера и выкинуть кэш, не дожидаясь истечения TTL.
        customers.invalidate(service["id"])
        return {"ok": True}

    # ── File upload ───────────────────────────────────────────────────────────

    @app.post("/api/upload")
    async def upload_file(file: UploadFile = File(...), operator: dict = Depends(require_auth)):
        ext = Path(file.filename).suffix if file.filename else ""
        filename = f"{uuid.uuid4().hex}{ext}"
        content = await file.read()
        url = await storage.save(content, filename)
        return {"url": url, "filename": filename}

    @app.post("/api/n8n/upload")
    async def n8n_upload(
        request: Request,
        file: UploadFile = File(...),
    ):
        key = request.headers.get("X-API-Key", "")
        if not settings.N8N_API_KEY or key != settings.N8N_API_KEY:
            raise HTTPException(401, "Invalid API key")
        ext = Path(file.filename).suffix if file.filename else ""
        filename = f"{uuid.uuid4().hex}{ext}"
        content = await file.read()
        url = await storage.save(content, filename)
        return {"url": url, "filename": filename}

    # ── Состояние серверов и ботов ────────────────────────────────────────────

    @app.get("/api/health")
    async def get_health(service_id: Optional[int] = None,
                         operator: dict = Depends(require_auth)):
        """С service_id — состояние одного ВПН-а; без него сводка по всем
        доступным оператору (режим «Все сервисы»). Доступно всем операторам —
        каждый видит только свои сервисы."""
        ids = await db.get_operator_service_ids(operator)
        if service_id is not None:
            if service_id not in ids:
                raise HTTPException(403, "Нет доступа к этому сервису")
            ids = [service_id]
        services = {s["id"]: s for s in await db.get_services()}
        out = []
        for sid in ids:
            service = services.get(sid)
            if service:
                out.append(await health.ensure(service))
        return {"services": out, "isMock": any(s.get("isMock") for s in out),
                "serversMock": any(s.get("serversMock") for s in out),
                "botsMock": any(s.get("botsMock") for s in out)}

    @app.post("/api/health/refresh")
    async def refresh_health(service_id: Optional[int] = None,
                             operator: dict = Depends(require_auth)):
        """Кнопка «Обновить»: внеочередной опрос вместо ожидания цикла."""
        ids = await db.get_operator_service_ids(operator)
        if service_id is not None:
            if service_id not in ids:
                raise HTTPException(403, "Нет доступа к этому сервису")
            ids = [service_id]
        services = {s["id"]: s for s in await db.get_services()}
        out = [await health.refresh(services[sid]) for sid in ids if sid in services]
        return {"services": out, "isMock": any(s.get("isMock") for s in out),
                "serversMock": any(s.get("serversMock") for s in out),
                "botsMock": any(s.get("botsMock") for s in out)}

    @app.get("/api/settings/monitoring")
    async def get_monitoring(service_id: Optional[int] = None,
                             operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        service = await require_service(service_id, operator)
        stored = await db.get_setting_json("monitoring", None, service["id"]) or {}
        return {**MONITORING_DEFAULTS, **stored,
                "serviceId": service["id"], "serviceName": service["name"],
                # Список зарегистрированных источников — админка строит выбор по
                # нему, поэтому свой провайдер появляется в UI сам собой.
                "available": {"servers": known_providers("servers"),
                              "bots": known_providers("bots")}}

    @app.put("/api/settings/monitoring")
    async def save_monitoring(body: MonitoringBody, service_id: Optional[int] = None,
                              operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        service = await require_service(service_id, operator)
        data = body.model_dump()
        await db.set_setting_json("monitoring", data, service["id"])
        # Подхватить новый источник сразу, не дожидаясь цикла опроса.
        asyncio.create_task(health.refresh(service))
        return {"ok": True}

    # ── Statistics ────────────────────────────────────────────────────────────

    @app.get("/api/stats")
    async def get_stats(days: int = 14, service_id: Optional[int] = None,
                        operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        return await db.get_stats(days, await _stats_scope(service_id, operator))

    @app.get("/api/stats/times")
    async def get_time_stats(days: int = 30, service_id: Optional[int] = None,
                             operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        return await db.get_time_stats(days, await _stats_scope(service_id, operator))

    async def _stats_scope(service_id: Optional[int], operator: dict) -> list[int]:
        """Статистика по одному сервису или сводная по всем доступным."""
        ids = await db.get_operator_service_ids(operator)
        if service_id is None:
            return ids
        if service_id not in ids:
            raise HTTPException(403, "Нет доступа к этому сервису")
        return [service_id]

    # ── Services (ВПН-ы) ──────────────────────────────────────────────────────

    def _fmt_service(s: dict, count: int = 0, api: dict = None, fb: dict = None,
                     mon: dict = None) -> dict:
        cfg = (api or {}).get("config") or {}
        fb_cfg = (fb or {}).get("config") or {}
        # Remnawave для мониторинга серверов — это monitoring.servers, отдельная
        # от customer настройка: с источником данных о клиенте она не связана.
        rw_block = (mon or {}).get("servers") or {}
        rw_cfg = rw_block.get("config") or {}
        rw_active = rw_block.get("provider") == "remnawave"
        return {
            "id": s["id"], "slug": s["slug"], "name": s["name"],
            "color": s["color"], "emoji": s.get("emoji"),
            "qdrantCollection": s["qdrant_collection"],
            "dialogIdPrefix": s["dialog_id_prefix"],
            "n8nWebhookUrl": s.get("n8n_webhook_url") or "",
            "businessId": s.get("business_connection_id") or "",
            "isActive": s["is_active"], "sortOrder": s["sort_order"],
            "activeCount": count,
            # Токен наружу не отдаём никогда: форма показывает «сохранён» и
            # отправляет пустое поле, если менять его не собираются.
            "apiBaseUrl": cfg.get("base_url") or "",
            "hasApiToken": bool(cfg.get("token")),
            # Remnawave для статистики серверов (экран «Состояние») — только
            # когда в monitoring.servers выбран именно remnawave.
            "remnawaveBaseUrl": rw_cfg.get("base_url") or "" if rw_active else "",
            "hasRemnawaveToken": bool(rw_cfg.get("token")) if rw_active else False,
            "hasRemnawaveCookie": bool(rw_cfg.get("cookie")) if rw_active else False,
            # Резервная отправка. app_hash и строка сессии — секреты и наружу не
            # уходят никогда, ровно как токен Support API.
            "fallbackEnabled": bool((fb or {}).get("enabled")),
            "fallbackAppId": fb_cfg.get("app_id") or "",
            "fallbackPhone": fb_cfg.get("phone") or "",
            "fallbackAccount": fb_cfg.get("account") or "",
            "hasFallbackSession": bool(fb_cfg.get("session")),
        }

    async def _save_service_api(service_id: int, base_url: str, token: str) -> None:
        """URL и токен Support API живут в настройке `customer` того же сервиса
        — там же, где их ищет карточка клиента. Пустой токен означает «не
        трогать сохранённый», иначе правка названия стирала бы доступ."""
        stored = await db.get_setting_json("customer", None, service_id) or {}
        cfg = dict(stored.get("config") or {})
        base_url = (base_url or "").strip().rstrip("/")
        if not base_url and not token:
            return
        cfg["base_url"] = base_url or cfg.get("base_url", "")
        if token:
            cfg["token"] = token.strip()
        # remnawave и http выбирают осознанно на экране «Клиенты», и форма
        # сервиса их не перебивает. Всё остальное (в том числе мок по
        # умолчанию) при заполненном URL становится Support API.
        provider = stored.get("provider")
        await db.set_setting_json("customer", {
            **CUSTOMER_DEFAULTS, **stored,
            "provider": provider if provider in ("remnawave", "http") else "bot_api",
            "config": cfg,
        }, service_id)
        customers.invalidate(service_id)

    async def _save_service_remnawave(service: dict, base_url: str, token: str,
                                      cookie: str = "") -> None:
        """Remnawave-поля формы сервиса — ИСКЛЮЧИТЕЛЬНО источник статистики
        серверов на экране «Состояние» (`monitoring.servers`). С профилем
        клиента (`customer`, вкладки Профиль/Ключи в карточке) это никак не
        связано и переключать `customer.provider` эта функция не имеет права
        — источник данных о клиенте настраивается отдельно, в «Настройки →
        Источник данных». Пустые токен/cookie при правке — «не трогать
        сохранённые», как и у Support API. Cookie нужна, только если панель
        стоит за прокси/WAF, требующим статический заголовок Cookie."""
        base_url = (base_url or "").strip().rstrip("/")
        token = (token or "").strip()
        cookie = (cookie or "").strip()
        if not base_url and not token and not cookie:
            return
        service_id = service["id"]

        stored_m = await db.get_setting_json("monitoring", None, service_id) or {}
        monitoring = {**MONITORING_DEFAULTS, **stored_m}
        servers_block = dict(monitoring.get("servers") or {})
        cfg_s = dict(servers_block.get("config") or {})
        cfg_s["base_url"] = base_url or cfg_s.get("base_url", "")
        if token:
            cfg_s["token"] = token
        if cookie:
            cfg_s["cookie"] = cookie
        monitoring["servers"] = {"provider": "remnawave", "config": cfg_s}
        await db.set_setting_json("monitoring", monitoring, service_id)

        asyncio.create_task(health.refresh(service))

    async def _check_business_id_free(business_id: str, service_id: int | None) -> None:
        """Один аккаунт поддержки — один ВПН. В БД это стережёт уникальный
        индекс, но человеку нужен внятный текст, а не ошибка драйвера."""
        business_id = (business_id or "").strip()
        if not business_id:
            return
        other = await db.get_service_by_business_id(business_id)
        if other and other["id"] != service_id:
            raise HTTPException(409, f"Этот business_id уже занят сервисом «{other['name']}»")

    @app.post("/api/services/test-connection")
    async def test_service_connection(body: ApiCheckBody,
                                      operator: dict = Depends(require_auth)):
        """Проверка адреса и токена до сохранения сервиса: дёргаем /meta и
        показываем, что за бот ответил. Дешевле, чем завести сервис с опечаткой
        в токене и выяснить это на живом клиенте."""
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        base_url = (body.base_url or "").strip().rstrip("/")
        if not base_url:
            raise HTTPException(400, "Укажите адрес API")
        token = (body.token or "").strip()
        cookie = (body.cookie or "").strip()
        if body.service_id is not None and (not token or (body.provider == "remnawave" and not cookie)):
            # Токен (и кука у remnawave) наружу не отдаются, поэтому форма
            # правки шлёт их пустыми: берём сохранённые оттуда же, куда их
            # кладёт соответствующий _save_service_* — bot_api в
            # customer.config, remnawave в monitoring.servers.config (это
            # разные настройки, не путать).
            if body.provider == "remnawave":
                stored = await db.get_setting_json("monitoring", None, body.service_id) or {}
                saved_cfg = (stored.get("servers") or {}).get("config") or {}
                token = token or saved_cfg.get("token") or ""
                cookie = cookie or saved_cfg.get("cookie") or ""
            else:
                stored = await db.get_setting_json("customer", None, body.service_id) or {}
                token = token or (stored.get("config") or {}).get("token") or ""

        if body.provider == "remnawave":
            try:
                info = await _remnawave_check_connection(base_url, token, cookie or None)
            except Exception as e:
                return {"ok": False, "error": str(e)[:200]}
            return {"ok": True, "botName": f"Remnawave v{info['version']}" if info["version"] else "Remnawave",
                    "scopes": [f"{info['nodesTotal']} нод"]}

        provider = build_customer_provider(
            "bot_api", {}, {"base_url": base_url, "token": token})
        if not provider:
            raise HTTPException(500, "Провайдер bot_api не зарегистрирован")
        try:
            meta = await provider.meta()
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}
        return {"ok": True, "botId": meta.get("bot_id") or "",
                "botName": meta.get("bot_name") or "",
                "scopes": meta.get("scopes") or []}

    @app.get("/api/services")
    async def get_services(operator: dict = Depends(require_auth)):
        """Сервисы, доступные оператору, со счётчиком «новые + непрочитанные»
        для бейджа на пилюле переключателя."""
        ids = await db.get_operator_service_ids(operator)
        counts = await db.get_service_counts(ids)
        services = [s for s in await db.get_services() if s["id"] in ids]
        return [_fmt_service(s, counts.get(s["id"], 0)) for s in services]

    @app.get("/api/services/all")
    async def get_all_services(operator: dict = Depends(require_auth)):
        """Полный список для админки — включая выключенные сервисы. Вместе с
        адресом Support API, чтобы форма подключения открывалась заполненной."""
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        out = []
        for s in await db.get_services(only_active=False):
            api = await db.get_setting_json("customer", None, s["id"]) or {}
            fb = await db.get_setting_json("fallback_sender", None, s["id"]) or {}
            mon = await db.get_setting_json("monitoring", None, s["id"]) or {}
            out.append(_fmt_service(s, 0, api, fb, mon))
        return out

    @app.post("/api/services")
    async def create_service(body: ServiceBody, operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        if not body.name.strip():
            raise HTTPException(400, "Название обязательно")
        try:
            slug = _validate_slug(body.slug)
        except ValueError as e:
            raise HTTPException(400, str(e))
        if await db.get_service_by_slug(slug):
            raise HTTPException(409, "Сервис с таким слагом уже есть")
        await _check_business_id_free(body.business_id, None)
        service = await db.create_service(
            slug, body.name.strip(), body.color, body.emoji, body.n8n_webhook_url,
            body.business_id,
        )
        await _save_service_api(service["id"], body.api_base_url, body.api_token)
        await _save_service_remnawave(service, body.remnawave_base_url, body.remnawave_token, body.remnawave_cookie)
        # Пустая коллекция создаётся сразу — воркфлоу n8n сможет обращаться к
        # ней ещё до первой загрузки базы знаний.
        try:
            from app.kb import ensure_collection
            await ensure_collection(settings.QDRANT_URL, service["qdrant_collection"])
        except Exception as e:
            print(f"[services] ensure_collection failed: {e}")
        await ws.broadcast({"type": "services_changed"})
        return _fmt_service(service, 0,
                            await db.get_setting_json("customer", None, service["id"]),
                            await db.get_setting_json("fallback_sender", None, service["id"]),
                            await db.get_setting_json("monitoring", None, service["id"]))

    @app.put("/api/services/{service_id}")
    async def update_service(service_id: int, body: ServiceBody,
                             operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        if not body.name.strip():
            raise HTTPException(400, "Название обязательно")
        await _check_business_id_free(body.business_id, service_id)
        service = await db.update_service(
            service_id, body.name.strip(), body.color, body.emoji,
            body.n8n_webhook_url, body.is_active, body.business_id,
        )
        if not service:
            raise HTTPException(404)
        await _save_service_api(service_id, body.api_base_url, body.api_token)
        await _save_service_remnawave(service, body.remnawave_base_url, body.remnawave_token, body.remnawave_cookie)
        await ws.broadcast({"type": "services_changed"})
        return _fmt_service(service, 0,
                            await db.get_setting_json("customer", None, service_id),
                            await db.get_setting_json("fallback_sender", None, service_id),
                            await db.get_setting_json("monitoring", None, service_id))

    @app.delete("/api/services/{service_id}")
    async def delete_service(service_id: int, operator: dict = Depends(require_auth)):
        """Удаление сервиса уносит его диалоги, сообщения и статьи БЗ — поэтому
        последний сервис удалить нельзя, иначе входящим некуда попадать."""
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        service = await db.get_service(service_id)
        if not service:
            raise HTTPException(404)
        if len(await db.get_services(only_active=False)) <= 1:
            raise HTTPException(400, "Нельзя удалить единственный сервис")
        await db.delete_service(service_id)
        try:
            from app.kb import delete_collection
            await delete_collection(settings.QDRANT_URL, service["qdrant_collection"])
        except Exception as e:
            print(f"[services] delete_collection failed: {e}")
        await ws.broadcast({"type": "services_changed"})
        return {"ok": True}

    # ── Резервная отправка ────────────────────────────────────────────────────
    # Ответ оператора уходит через n8n в business-чат Telegram, и тот иногда
    # отвечает BUSINESS_PEER_USAGE_MISSING. Резервный канал шлёт то же самое по
    # MTProto от того же аккаунта поддержки — клиент видит сообщение в той же
    # переписке. Настраивается в форме сервиса.

    async def _require_fallback(service_id: int, operator: dict) -> dict:
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        if not fallback:
            raise HTTPException(503, "Резервная отправка не собрана в этой установке")
        service = await db.get_service(service_id)
        if not service:
            raise HTTPException(404, "Сервис не найден")
        return service

    @app.post("/api/services/{service_id}/fallback/send-code")
    async def fallback_send_code(service_id: int, body: FallbackAuthBody,
                                 operator: dict = Depends(require_auth)):
        await _require_fallback(service_id, operator)
        try:
            return await fallback.send_code(service_id, body.app_id, body.app_hash,
                                            body.phone.strip())
        except Exception as e:
            raise HTTPException(400, str(e)[:200])

    @app.post("/api/services/{service_id}/fallback/sign-in")
    async def fallback_sign_in(service_id: int, body: FallbackCodeBody,
                               operator: dict = Depends(require_auth)):
        await _require_fallback(service_id, operator)
        try:
            return await fallback.sign_in(service_id, body.code.strip(), body.password)
        except Exception as e:
            raise HTTPException(400, str(e)[:200])

    @app.post("/api/services/{service_id}/fallback/session")
    async def fallback_set_session(service_id: int, body: FallbackSessionBody,
                                   operator: dict = Depends(require_auth)):
        """Строка сессии, сгенерированная снаружи. Сразу проверяем её боем: без
        проверки админ узнал бы об опечатке на первом же несработавшем фолбеке."""
        await _require_fallback(service_id, operator)
        stored = await fallback.settings(service_id)
        await fallback.save(service_id, {
            **stored, "enabled": True,
            "config": {**(stored.get("config") or {}), "app_id": body.app_id,
                       "app_hash": body.app_hash, "phone": body.phone.strip(),
                       "session": body.session.strip(), "account": ""},
        })
        result = await fallback.check(service_id)
        if result.get("ok"):
            fresh = await fallback.settings(service_id)
            await fallback.save(service_id, {
                **fresh, "config": {**(fresh.get("config") or {}),
                                    "account": result.get("account") or ""}})
        return result

    @app.post("/api/services/{service_id}/fallback/test")
    async def fallback_test(service_id: int, operator: dict = Depends(require_auth)):
        await _require_fallback(service_id, operator)
        return await fallback.check(service_id)

    @app.patch("/api/services/{service_id}/fallback")
    async def fallback_toggle(service_id: int, body: FallbackToggleBody,
                              operator: dict = Depends(require_auth)):
        await _require_fallback(service_id, operator)
        stored = await fallback.settings(service_id)
        await fallback.save(service_id, {**stored, "enabled": body.enabled})
        return {"ok": True, "enabled": body.enabled}

    @app.delete("/api/services/{service_id}/fallback")
    async def fallback_forget(service_id: int, operator: dict = Depends(require_auth)):
        """Отвязать аккаунт: сессия удаляется, канал выключается."""
        await _require_fallback(service_id, operator)
        await fallback.save(service_id, {"enabled": False, "config": {}})
        return {"ok": True}

    # ── Папки тикетов ─────────────────────────────────────────────────────────
    # Папка — второй срез списка поверх статусов: тикет остаётся в «В работе»
    # или «Ожидании» и дополнительно лежит в папке, куда его положил оператор.
    # Создаёт и правит папки админ, раскладывает по ним — любой оператор.

    def _fmt_folder(f: dict) -> dict:
        return {"id": f["id"], "serviceId": f["service_id"], "name": f["name"],
                "emoji": f.get("emoji") or "📁", "color": f.get("color") or "#4F8EF7",
                "sortOrder": f.get("sort_order") or 0,
                "openCount": int(f.get("open_count") or 0)}

    async def require_folder(folder_id: int, operator: dict) -> dict:
        folder = await db.get_folder(folder_id)
        if not folder:
            raise HTTPException(404, "Папка не найдена")
        if folder["service_id"] not in await db.get_operator_service_ids(operator):
            raise HTTPException(403, "Нет доступа к этому сервису")
        return folder

    @app.get("/api/folders")
    async def get_folders(service_id: Optional[int] = None,
                          operator: dict = Depends(require_auth)):
        """С service_id — папки одного ВПН-а; без него — всех доступных."""
        ids = await db.get_operator_service_ids(operator)
        if service_id is not None:
            if service_id not in ids:
                raise HTTPException(403, "Нет доступа к этому сервису")
            ids = [service_id]
        return [_fmt_folder(f) for f in await db.get_folders(ids)]

    @app.post("/api/folders")
    async def create_folder(body: FolderBody, service_id: Optional[int] = None,
                            operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        if not body.name.strip():
            raise HTTPException(400, "Название обязательно")
        service = await require_service(service_id, operator)
        folder = await db.create_folder(service["id"], body.name.strip(),
                                        body.emoji.strip() or "📁", body.color)
        await ws.broadcast({"type": "folders_changed", "service_id": service["id"]})
        return _fmt_folder(folder)

    @app.put("/api/folders/{folder_id}")
    async def update_folder(folder_id: int, body: FolderBody,
                            operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        folder = await require_folder(folder_id, operator)
        if not body.name.strip():
            raise HTTPException(400, "Название обязательно")
        updated = await db.update_folder(folder_id, body.name.strip(),
                                         body.emoji.strip() or "📁", body.color,
                                         body.sort_order)
        await ws.broadcast({"type": "folders_changed", "service_id": folder["service_id"]})
        return _fmt_folder(updated)

    @app.delete("/api/folders/{folder_id}")
    async def delete_folder(folder_id: int, operator: dict = Depends(require_auth)):
        """Тикеты из удалённой папки не пропадают — просто перестают быть
        разложенными (folder_id → NULL по внешнему ключу)."""
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        folder = await require_folder(folder_id, operator)
        await db.delete_folder(folder_id)
        await ws.broadcast({"type": "folders_changed", "service_id": folder["service_id"]})
        return {"ok": True}

    @app.post("/api/dialogs/{dialog_id}/folder")
    async def set_dialog_folder(dialog_id: str, body: DialogFolderBody,
                                operator: dict = Depends(require_auth)):
        dialog = await require_dialog_write(dialog_id, operator)
        if body.folder_id is not None:
            folder = await require_folder(body.folder_id, operator)
            if folder["service_id"] != dialog["service_id"]:
                raise HTTPException(400, "Папка другого сервиса")
        await db.set_dialog_folder(dialog_id, body.folder_id)
        updated = await db.get_dialog(dialog_id)
        await ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)},
                           updated["service_id"])
        return {"ok": True, "folderId": body.folder_id}

    # ── Operators ─────────────────────────────────────────────────────────────

    @app.get("/api/operators")
    async def get_operators(operator: dict = Depends(require_auth)):
        ops = await db.get_operators()
        result = []
        for op in ops:
            fmt = _fmt_operator(op)
            fmt["serviceIds"] = await db.get_operator_flag_ids(op["id"])
            result.append(fmt)
        return result

    @app.put("/api/operators/{op_id}/services")
    async def set_operator_services(op_id: int, body: OperatorServicesBody,
                                    operator: dict = Depends(require_auth)):
        """Флаги доступа к ВПН-ам. Снятый флаг возвращает тикеты оператора в
        этом сервисе в очередь, новый — сразу подключает его к раздаче."""
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        target = await db.get_operator(op_id)
        if not target:
            raise HTTPException(404)
        known = {s["id"] for s in await db.get_services(only_active=False)}
        unknown = [sid for sid in body.service_ids if sid not in known]
        if unknown:
            raise HTTPException(400, f"Неизвестные сервисы: {unknown}")
        removed = await db.set_operator_services(op_id, body.service_ids)
        for sid in removed:
            await routing.release_operator_service(target["name"], sid)
        ws.set_operator_services(op_id, await db.get_operator_service_ids(target))
        await ws.send_to_operator(op_id, {"type": "services_changed"})
        await routing.emit_counts()
        asyncio.create_task(routing.drain())
        return {"ok": True, "service_ids": body.service_ids}

    @app.get("/api/operators/me/notifications")
    async def get_my_notif_prefs(operator: dict = Depends(require_auth)):
        return _fmt_operator(operator)["notifPrefs"]

    @app.put("/api/operators/me/notifications")
    async def save_my_notif_prefs(body: NotifPrefsBody, operator: dict = Depends(require_auth)):
        await db.update_operator_notif_prefs(operator["id"], body.model_dump())
        return {"ok": True}

    @app.patch("/api/operators/me/pause")
    async def set_my_pause(body: PauseBody, operator: dict = Depends(require_auth)):
        await db.set_operator_paused(operator["id"], body.paused)
        await ws.broadcast({
            "type": "operator_status",
            "op_id": operator["id"],
            "online": operator.get("online", False),
            "paused": body.paused,
        })
        if not body.paused:
            asyncio.create_task(routing.drain())
        return {"ok": True, "paused": body.paused}

    @app.post("/api/operators")
    async def create_operator(body: OperatorBody, operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        op = await db.create_operator(body.name, body.tg, body.role, tg_id=body.tg_id)
        if body.password:
            if len(body.password) < 6:
                raise HTTPException(400, "Password must be at least 6 characters")
            await db.set_password(op["id"], hash_password(body.password))
        if body.service_ids:
            await db.set_operator_services(op["id"], body.service_ids)
        result = _fmt_operator(op)
        result["serviceIds"] = await db.get_operator_flag_ids(op["id"])
        return result

    @app.put("/api/operators/{op_id}")
    async def update_operator(op_id: int, body: OperatorBody, operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        result = await db.update_operator(op_id, body.name, body.tg, body.role, tg_id=body.tg_id)
        if not result:
            raise HTTPException(404)
        fmt = _fmt_operator(result)
        fmt["serviceIds"] = await db.get_operator_flag_ids(op_id)
        return fmt

    @app.delete("/api/operators/{op_id}")
    async def delete_operator(op_id: int, operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        if op_id == operator["id"]:
            raise HTTPException(400, "Cannot delete yourself")
        ok = await db.delete_operator(op_id)
        if not ok:
            raise HTTPException(404)
        return {"ok": True}

    # ── Settings: AI ──────────────────────────────────────────────────────────

    @app.get("/api/settings/ai")
    async def get_ai_settings(service_id: Optional[int] = None,
                              operator: dict = Depends(require_auth)):
        service = await require_service(service_id, operator)
        stored = await db.get_setting_json("ai_settings", None, service["id"]) or {}
        # merge so settings saved before 'model' existed still expose the default
        return {**_AI_DEFAULTS, **stored, "serviceId": service["id"], "serviceName": service["name"]}

    async def _sync_ai_settings_to_redis(ai: dict, service: dict):
        """Push AI settings to the Redis copy the n8n agent reads. The responder
        prompt goes out raw; the gate/handoff instruction is published as a
        separate `handoff_prompt` field the n8n gate node reads on its own — no
        concatenation. An emptied-out instruction falls back to the default so
        the gate never loses its routing criteria. EVERY endpoint that rewrites
        vpn_bot:<slug>:ai_settings must go through here.

        Ключ пер-сервисный: у каждого ВПН-а свой воркфлоу n8n и свой промпт."""
        automation = await db.get_setting_json("automation", None, service["id"]) or {}
        n8n_data = dict(ai)
        n8n_data["prompt"] = ai.get("prompt") or ""
        n8n_data["handoff_prompt"] = (
            (automation.get("handoff_instruction_text") or "").strip()
            or _AUTOMATION_DEFAULTS["handoff_instruction_text"]
        )
        await n8n.redis.set(
            f"vpn_bot:{service['slug']}:ai_settings", json.dumps(n8n_data, ensure_ascii=False)
        )

    @app.put("/api/settings/ai")
    async def save_ai_settings(body: AISettingsBody, service_id: Optional[int] = None,
                               operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        service = await require_service(service_id, operator)
        data = body.model_dump()
        await db.set_setting_json("ai_settings", data, service["id"])
        await _sync_ai_settings_to_redis(data, service)
        return {"ok": True}

    # ── Settings: Schedule ────────────────────────────────────────────────────

    @app.get("/api/settings/schedule")
    async def get_schedule(service_id: Optional[int] = None,
                           operator: dict = Depends(require_auth)):
        service = await require_service(service_id, operator)
        return await db.get_setting_json("schedule", _SCHEDULE_DEFAULTS, service["id"])

    @app.put("/api/settings/schedule")
    async def save_schedule(body: ScheduleBody, service_id: Optional[int] = None,
                            operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        service = await require_service(service_id, operator)
        await db.set_setting_json("schedule", body.schedule, service["id"])
        await n8n.redis.set(
            f"vpn_bot:{service['slug']}:schedule", json.dumps(body.schedule, ensure_ascii=False)
        )
        return {"ok": True}

    # ── Knowledge Base ────────────────────────────────────────────────────────

    @app.get("/api/kb")
    async def get_kb(service_id: Optional[int] = None, operator: dict = Depends(require_auth)):
        service = await require_service(service_id, operator)
        articles = await db.get_kb_articles(service["id"])
        for a in articles:
            try:
                a["keywords"] = json.loads(a["keywords"])
            except Exception:
                a["keywords"] = []
        return articles

    @app.post("/api/kb/upload")
    async def upload_kb(file: UploadFile = File(...), service_id: Optional[int] = None,
                        operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        service = await require_service(service_id, operator)
        if not settings.OPENAI_API_KEY:
            raise HTTPException(400, "OPENAI_API_KEY is required for embeddings")
        if not file.filename.endswith((".txt", ".md")):
            raise HTTPException(400, "Only .txt and .md files are supported")
        text = (await file.read()).decode("utf-8", errors="ignore")
        if not text.strip():
            raise HTTPException(400, "File is empty")
        # У каждого сервиса своя коллекция Qdrant — базы знаний не смешиваются.
        # db+service_id заставляют process_document полностью заменить прежнюю
        # базу знаний сервиса новой — иначе разделы, удалённые из документа при
        # правке, навсегда оставались бы в поиске ИИ.
        chunks = await process_document(
            text, kb_chat_client, settings.OPENAI_API_KEY, settings.QDRANT_URL,
            service["qdrant_collection"], db=db, service_id=service["id"],
        )
        for c in chunks:
            await db.save_kb_article(
                c["id"], c["title"], c["category"],
                json.dumps(c["keywords"], ensure_ascii=False),
                c["content"], service["id"],
            )
        return {"chunks_created": len(chunks), "ids": [c["id"] for c in chunks]}

    @app.delete("/api/kb")
    async def reset_kb_all(service_id: Optional[int] = None,
                           operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        service = await require_service(service_id, operator)
        from app.kb import delete_collection, ensure_collection
        await db.reset_kb(service["id"])
        await delete_collection(settings.QDRANT_URL, service["qdrant_collection"])
        await ensure_collection(settings.QDRANT_URL, service["qdrant_collection"])
        return {"ok": True}

    @app.delete("/api/kb/{article_id}")
    async def delete_kb_article(article_id: str, service_id: Optional[int] = None,
                                operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        service = await require_service(service_id, operator)
        ok = await db.delete_kb_article(article_id, service["id"])
        if not ok:
            raise HTTPException(404)
        await delete_from_qdrant(article_id, settings.QDRANT_URL, service["qdrant_collection"])
        return {"ok": True}

    # ── Settings: Sounds ─────────────────────────────────────────────────────

    @app.get("/api/settings/sounds")
    async def get_sounds(operator: dict = Depends(require_auth)):
        return await db.get_setting_json("sounds", {})

    @app.post("/api/settings/sounds/upload")
    async def upload_sound(
        event: str,
        file: UploadFile = File(...),
        operator: dict = Depends(require_auth),
    ):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        if event not in ("operator_called", "new_message"):
            raise HTTPException(400, "event must be operator_called or new_message")
        ext = Path(file.filename).suffix if file.filename else ".mp3"
        filename = f"sound_{event}_{uuid.uuid4().hex}{ext}"
        content = await file.read()
        url = await storage.save(content, filename)
        sounds = await db.get_setting_json("sounds", {})
        sounds[f"{event}_url"] = url
        await db.set_setting_json("sounds", sounds)
        return {"url": url}

    # ── Settings: Automation ─────────────────────────────────────────────────

    @app.get("/api/settings/automation")
    async def get_automation(service_id: Optional[int] = None,
                             operator: dict = Depends(require_auth)):
        service = await require_service(service_id, operator)
        stored = await db.get_setting_json("automation", None, service["id"]) or {}
        # merge so settings saved before new keys existed still expose defaults
        return {**_AUTOMATION_DEFAULTS, **stored,
                "serviceId": service["id"], "serviceName": service["name"]}

    @app.put("/api/settings/automation")
    async def save_automation(body: AutomationSettingsBody, service_id: Optional[int] = None,
                              operator: dict = Depends(require_auth)):
        """Вся вкладка «Автоматизация» настраивается отдельно у каждого ВПН-а —
        включая лимит тикетов на оператора и грейс офлайна."""
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        service = await require_service(service_id, operator)
        data = body.model_dump()
        await db.set_setting_json("automation", data, service["id"])
        # Синхронизировать auto_handoff_enabled → ai_settings для консьюмеров
        # (get_setting_json returns the default object AS-IS when nothing is
        # stored yet — never mutate it in place, or the process-wide default
        # gets corrupted on the very first save of a fresh install)
        ai = await db.get_setting_json("ai_settings", None, service["id"]) or dict(_AI_DEFAULTS)
        ai["handoff_enabled"] = data["auto_handoff_enabled"]
        await db.set_setting_json("ai_settings", ai, service["id"])
        # через общий хелпер — иначе инструкция эскалации пропадёт из промпта
        await _sync_ai_settings_to_redis(ai, service)
        # Лимит слотов мог вырасти — раздать очередь по новой ёмкости.
        asyncio.create_task(routing.drain())
        return {"ok": True}

    # ── Broadcast ─────────────────────────────────────────────────────────────

    @app.post("/api/broadcast")
    async def broadcast_msg(body: BroadcastBody, service_id: Optional[int] = None,
                            operator: dict = Depends(require_auth)):
        """Рассылка идёт клиентам ОДНОГО сервиса и уходит через его бота.
        Лок тоже пер-сервисный — рассылка в одном ВПН-е не блокирует другой."""
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        service = await require_service(service_id, operator)
        if not body.text.strip():
            raise HTTPException(400, "Текст не может быть пустым")
        lock_key = f"vpn_bot:broadcast_lock:{service['slug']}"
        if await n8n.redis.get(lock_key):
            raise HTTPException(429, "Рассылка уже выполняется")
        await n8n.redis.set(lock_key, "1", ex=30)
        chat_ids = await db.get_all_chat_ids(service["id"])
        sent = 0
        failed = 0
        try:
            for cid in chat_ids:
                ok = await n8n.send_to_user(cid, body.text, service=service)
                if ok:
                    sent += 1
                else:
                    failed += 1
        finally:
            await n8n.redis.delete(lock_key)
        # Rate-limiting (30 msg/sec Telegram limit) is handled by n8n — add a
        # 50 ms Wait node between iterations in the "Send to User" workflow.
        return {"sent": sent, "failed": failed, "total": len(chat_ids)}

    # ── Templates ─────────────────────────────────────────────────────────────

    @app.get("/api/templates")
    async def get_templates(service_id: Optional[int] = None,
                            operator: dict = Depends(require_auth)):
        service = await require_service(service_id, operator)
        return await db.get_templates(service["id"])

    @app.post("/api/templates")
    async def create_template(body: TemplateBody, service_id: Optional[int] = None,
                              operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        service = await require_service(service_id, operator)
        if not body.title.strip() or not body.text.strip():
            raise HTTPException(400, "Название и текст обязательны")
        return await db.save_template(
            None, body.group_name.strip() or "Общие", body.title.strip(), body.text.strip(),
            service["id"],
        )

    @app.put("/api/templates/{template_id}")
    async def update_template(template_id: int, body: TemplateBody,
                              service_id: Optional[int] = None,
                              operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        service = await require_service(service_id, operator)
        row = await db.save_template(
            template_id, body.group_name.strip() or "Общие", body.title.strip(),
            body.text.strip(), service["id"],
        )
        if not row:
            raise HTTPException(404)
        return row

    @app.delete("/api/templates/{template_id}")
    async def delete_template_ep(template_id: int, service_id: Optional[int] = None,
                                 operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        service = await require_service(service_id, operator)
        ok = await db.delete_template(template_id, service["id"])
        if not ok:
            raise HTTPException(404)
        return {"ok": True}

    @app.patch("/api/templates/group")
    async def rename_template_group(body: RenameGroupBody, service_id: Optional[int] = None,
                                    operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        service = await require_service(service_id, operator)
        if not body.new_name.strip():
            raise HTTPException(400, "Название группы не может быть пустым")
        await db.rename_template_group(body.old_name.strip(), body.new_name.strip(), service["id"])
        return {"ok": True}

    # ── WebSocket ─────────────────────────────────────────────────────────────

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket, token: str = ""):
        op_id = decode_token(token, settings.SECRET_KEY)
        if not op_id:
            await websocket.close(code=4001)
            return
        op = await db.get_operator(op_id)
        if not op:
            await websocket.close(code=4001)
            return
        # Сокет запоминает доступные сервисы: события по чужим ВПН-ам на эту
        # вкладку не пойдут.
        went_online = await ws.connect(websocket, op_id, await db.get_operator_service_ids(op))
        await routing.emit_counts()
        if went_online:
            await db.set_operator_online(op_id, True)
            # back within the grace period — cancel the offline timer
            await db.set_operator_offline_since(op_id, False)
            await ws.broadcast({"type": "operator_status", "op_id": op_id, "online": True,
                                "paused": op.get("paused", False)})
            asyncio.create_task(routing.drain())
        try:
            while True:
                text = await websocket.receive_text()
                if text == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            departed_id, went_offline = ws.disconnect(websocket)
            if went_offline and departed_id:
                await db.set_operator_online(departed_id, False)
                # start the offline grace timer; the routing sweeper releases
                # the operator's in_progress tickets when it expires
                await db.set_operator_offline_since(departed_id, True)
                # last_seen проставлен в set_operator_online — перечитываем, чтобы
                # в списке операторов сразу встало «был в сети», а не «не заходил».
                departed = await db.get_operator(departed_id)
                await ws.broadcast({"type": "operator_status", "op_id": departed_id,
                                    "online": False, "paused": False,
                                    "last_seen": _fmt_operator(departed)["lastSeen"] if departed else None})

    return app
