import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Body, Depends, FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.ai_client import make_chat_client
from app.auth import create_token, decode_token, hash_password, verify_password
from app.billing import BillingProvider
from app.config import Settings
from app.database import SLUG_RE, DatabaseManager, avatar_color, make_initials
from app.kb import collection_name as kb_collection_name
from app.kb import delete_from_qdrant, process_document
from app.storage import make_storage
from app.summarizer import summarize_dialog
from app.n8n_client import N8NClient
from app.servers import ServerMonitor, StubServerMonitor
from app.ws_manager import WebSocketManager

_STATIC = Path(__file__).parent / "static"

_AI_DEFAULTS = {
    "prompt": (
        "Ты — дружелюбный ассистент поддержки VPN-сервиса. "
        "Отвечай кратко, на русском. "
        "Если не знаешь ответ — предложи передать диалог оператору."
    ),
    "temperature": 0.7,
    "auto_reply": True,
    "handoff_enabled": True,
    "classification_enabled": False,
}

_NOTIF_PREFS_DEFAULT = {"new_dialog": True, "operator_called": True, "server_down": True}

_SCHEDULE_DEFAULTS = {
    "mon": {"enabled": True,  "from": "09:00", "to": "21:00"},
    "tue": {"enabled": True,  "from": "09:00", "to": "21:00"},
    "wed": {"enabled": True,  "from": "09:00", "to": "21:00"},
    "thu": {"enabled": True,  "from": "09:00", "to": "21:00"},
    "fri": {"enabled": True,  "from": "09:00", "to": "21:00"},
    "sat": {"enabled": False, "from": "10:00", "to": "18:00"},
    "sun": {"enabled": False, "from": "10:00", "to": "18:00"},
}


# ── Formatters ────────────────────────────────────────────────────────────────

def _fmt_time(dt: datetime) -> str:
    if dt is None:
        return ""
    now = datetime.now(timezone.utc)
    dt_utc = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    diff = now - dt_utc
    if diff.days == 0:
        return dt_utc.strftime("%H:%M")
    if diff.days == 1:
        return "Вчера"
    return dt_utc.strftime("%d.%m")


def _fmt_dialog(row: dict, tickets: list = None) -> dict:
    did = row["dialog_id"]
    name = row.get("user_name") or row.get("external_id") or did
    username = row.get("user_username") or f"@{row['chat_id']}"
    return {
        "id": did,
        "externalId": row.get("external_id"),
        "serviceId": row.get("service_id"),
        "serviceSlug": row.get("service_slug"),
        "serviceName": row.get("service_name"),
        "serviceColor": row.get("service_color") or "#4F8EF7",
        "chatId": row["chat_id"],
        "name": name,
        "username": username,
        "tgId": row["chat_id"],
        "initials": make_initials(name),
        "avatarColor": avatar_color(did),
        "status": row["status"],
        "operatorCalled": row["operator_called"],
        "unread": row["unread_count"],
        "aiEnabled": row["ai_enabled"],
        "plan": row.get("user_plan") or "Basic",
        "subStatus": row.get("user_sub_status") or "active",
        "nextPayment": row.get("user_next_payment") or "—",
        "traffic": {
            "used": float(row.get("user_traffic_used") or 0),
            "total": float(row.get("user_traffic_total") or 100),
        },
        "lastPayment": {
            "amount": row.get("last_payment_amount") or "—",
            "date": row.get("last_payment_date") or "—",
        },
        "preview": row.get("last_message_text") or "",
        "time": _fmt_time(row.get("last_message_time")),
        "tickets": tickets or [],
    }


def _fmt_message(row: dict) -> dict:
    file_id = row.get("file_id")
    file_url = row.get("file_url")
    # handle legacy records where n8n put the URL into file_id
    if not file_url and file_id and str(file_id).startswith("http"):
        file_url, file_id = file_id, None
    return {
        "id": row["id"],
        "kind": row["kind"],
        "text": row.get("text") or "",
        "fileId": file_id,
        "fileType": row.get("file_type"),
        "fileUrl": file_url,
        "operator": row.get("operator_name"),
        "time": _fmt_time(row.get("created_at")),
    }


def _fmt_operator(op: dict, service_ids: list = None) -> dict:
    raw_prefs = op.get("notif_prefs")
    notif_prefs = json.loads(raw_prefs) if raw_prefs else _NOTIF_PREFS_DEFAULT
    return {
        "id": op["id"],
        "name": op["name"],
        "tg": op["tg"],
        "tgId": op.get("tg_id"),
        "role": op["role"],
        "initials": op.get("initials") or make_initials(op["name"]),
        "color": op.get("color") or "#4F8EF7",
        "online": op.get("online", False),
        "notifPrefs": notif_prefs,
        # The access flags. Admins are not flagged per service — the role
        # already grants every service.
        "serviceIds": service_ids or [],
    }


def _fmt_service(row: dict, counters: dict = None) -> dict:
    counts = (counters or {}).get(row["id"], {})
    return {
        "id": row["id"],
        "slug": row["slug"],
        "name": row["name"],
        "color": row["color"],
        "isDefault": row["is_default"],
        "isActive": row["is_active"],
        "kbCollection": kb_collection_name(row["slug"]),
        "openCount": counts.get("open", 0),
        "badgeCount": counts.get("badge", 0),
    }


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
    operator_name: str = "Оператор"
    file_url: Optional[str] = None
    file_type: Optional[str] = None

class HandoffBody(BaseModel):
    operator_name: str = "Оператор"

class OperatorBody(BaseModel):
    name: str
    tg: str
    tg_id: Optional[int] = None
    role: str = "agent"
    password: str = ""
    # Which VPN services this operator may answer tickets for. Ignored for
    # admins, who see everything by role.
    service_ids: Optional[list[int]] = None

class ServiceBody(BaseModel):
    name: str
    slug: str = ""
    color: str = ""
    is_active: bool = True

class OperatorServicesBody(BaseModel):
    service_ids: list[int] = []

class AISettingsBody(BaseModel):
    prompt: str
    temperature: float
    auto_reply: bool
    handoff_enabled: bool
    classification_enabled: bool = False

class NotifPrefsBody(BaseModel):
    new_dialog:      bool = True
    operator_called: bool = True
    server_down:     bool = True

class ScheduleBody(BaseModel):
    schedule: dict


# ── App factory ───────────────────────────────────────────────────────────────

def build_app(
    settings: Settings,
    db: DatabaseManager,
    ws: WebSocketManager,
    n8n: N8NClient,
    billing: BillingProvider,
    server_monitor: ServerMonitor,
) -> FastAPI:
    app = FastAPI(title="VPN Helpdesk")
    uploads = settings.uploads_path()
    chat_client = make_chat_client(settings.CHAT_PROVIDER, settings.OPENAI_API_KEY, settings.GEMINI_API_KEY)
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

    # ── Service access ────────────────────────────────────────────────────────

    async def allowed_service_ids(operator: dict) -> list[int]:
        """Services this operator may work with — the 'flags' from the brief."""
        if operator["role"] == "admin":
            return [s["id"] for s in await db.get_services()]
        return await db.get_operator_service_ids(operator["id"])

    async def require_dialog(dialog_id: str, operator: dict) -> dict:
        """Load a dialog, refusing it when the operator lacks the service flag."""
        dialog = await db.get_dialog(dialog_id)
        if not dialog:
            raise HTTPException(404, "Dialog not found")
        if dialog["service_id"] not in await allowed_service_ids(operator):
            raise HTTPException(403, "Нет доступа к этому сервису")
        return dialog

    async def require_service(slug: str, operator: dict) -> dict:
        """Resolve a ?service=slug parameter and check access."""
        service = await db.get_service_by_slug(slug)
        if not service:
            raise HTTPException(404, f"Unknown service: {slug}")
        if service["id"] not in await allowed_service_ids(operator):
            raise HTTPException(403, "Нет доступа к этому сервису")
        return service

    def require_admin(operator: dict) -> None:
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")

    # ── Static / index ────────────────────────────────────────────────────────

    @app.get("/")
    async def index():
        return FileResponse(_STATIC / "index.html")

    @app.get("/api/files/{filename}")
    async def serve_file(filename: str):
        # Uploads are named with uuid4 hex + extension. Reject anything else:
        # the path used to be joined raw, so "../" escaped the uploads dir.
        if Path(filename).name != filename or filename in ("", ".", ".."):
            raise HTTPException(400, "Invalid filename")
        path = (uploads / filename).resolve()
        if not path.is_relative_to(uploads.resolve()) or not path.is_file():
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
        return {"token": token, "operator": _fmt_operator(op, await allowed_service_ids(op))}

    @app.post("/api/auth/login")
    async def login(body: LoginBody):
        op = await db.get_operator_by_tg(body.tg)
        if not op or not op.get("password_hash"):
            raise HTTPException(401, "Неверный логин или пароль")
        if not verify_password(body.password, op["password_hash"]):
            raise HTTPException(401, "Неверный логин или пароль")
        token = create_token(op["id"], settings.SECRET_KEY)
        return {"token": token, "operator": _fmt_operator(op, await allowed_service_ids(op))}

    # ── Auth (protected) ──────────────────────────────────────────────────────

    @app.get("/api/auth/me")
    async def me(operator: dict = Depends(require_auth)):
        return _fmt_operator(operator, await allowed_service_ids(operator))

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

    # ── Services ──────────────────────────────────────────────────────────────

    def _ticket(t: dict) -> dict:
        return {
            "id": f"T-{t['dialog_id'][-4:]}",
            "dialogId": t["dialog_id"],
            "title": t.get("summary") or t["last_message_text"] or "Диалог",
            "date": _fmt_time(t["updated_at"]),
            "solved": True,
        }

    @app.get("/api/services")
    async def get_services(operator: dict = Depends(require_auth)):
        allowed = set(await allowed_service_ids(operator))
        counters = await db.get_service_counters()
        return [
            _fmt_service(s, counters)
            for s in await db.get_services()
            if s["id"] in allowed and (s["is_active"] or operator["role"] == "admin")
        ]

    @app.post("/api/services")
    async def create_service(body: ServiceBody, operator: dict = Depends(require_auth)):
        require_admin(operator)
        slug = (body.slug or body.name).strip().lower().replace(" ", "-")
        if not SLUG_RE.match(slug):
            raise HTTPException(
                400, "Идентификатор: 2–32 символа, латиница в нижнем регистре, цифры, - и _"
            )
        if await db.get_service_by_slug(slug):
            raise HTTPException(400, f"Сервис «{slug}» уже существует")
        service = await db.create_service(slug, body.name.strip(), body.color or None)
        return _fmt_service(service)

    @app.put("/api/services/{service_id}")
    async def update_service(service_id: int, body: ServiceBody, operator: dict = Depends(require_auth)):
        require_admin(operator)
        # slug is immutable: it is baked into dialog keys, Redis channel names
        # and the Qdrant collection, so renaming it would orphan live data.
        service = await db.update_service(
            service_id, body.name.strip(), body.color or "#4F8EF7", body.is_active
        )
        if not service:
            raise HTTPException(404)
        return _fmt_service(service)

    @app.delete("/api/services/{service_id}")
    async def delete_service(service_id: int, operator: dict = Depends(require_auth)):
        require_admin(operator)
        service = await db.get_service(service_id)
        if not service:
            raise HTTPException(404)
        if service["is_default"]:
            raise HTTPException(400, "Нельзя удалить сервис по умолчанию")
        count = await db.count_service_dialogs(service_id)
        if count:
            raise HTTPException(
                400,
                f"У сервиса {count} диалог(ов). Отключите его вместо удаления, "
                "чтобы не потерять переписку.",
            )
        await db.delete_service(service_id)
        return {"ok": True}

    # ── Dialogs ───────────────────────────────────────────────────────────────

    @app.get("/api/dialogs")
    async def get_dialogs(service: str = "", operator: dict = Depends(require_auth)):
        if service:
            service_ids = [(await require_service(service, operator))["id"]]
        else:
            service_ids = await allowed_service_ids(operator)
        rows = await db.get_dialogs_for(service_ids)
        return [_fmt_dialog(r) for r in rows]

    @app.get("/api/dialogs/{dialog_id}")
    async def get_dialog(dialog_id: str, operator: dict = Depends(require_auth)):
        row = await require_dialog(dialog_id, operator)
        tickets = await db.get_dialog_history(row["chat_id"], row["service_id"], dialog_id)
        return _fmt_dialog(row, [_ticket(t) for t in tickets])

    @app.get("/api/dialogs/{dialog_id}/history")
    async def get_dialog_history(dialog_id: str, operator: dict = Depends(require_auth)):
        row = await require_dialog(dialog_id, operator)
        history = await db.get_dialog_history(row["chat_id"], row["service_id"], dialog_id)
        return [_ticket(t) for t in history]

    @app.get("/api/dialogs/{dialog_id}/messages")
    async def get_messages(dialog_id: str, operator: dict = Depends(require_auth)):
        await require_dialog(dialog_id, operator)
        rows = await db.get_messages(dialog_id)
        return [_fmt_message(r) for r in rows]

    @app.post("/api/dialogs/{dialog_id}/read")
    async def mark_read(dialog_id: str, operator: dict = Depends(require_auth)):
        """Clear the unread counter.

        Split out of GET /messages: the client caches messages and never
        re-fetches them, so the old side effect only ever fired the first time
        a dialog was opened and the service badges drifted out of sync.
        """
        dialog = await require_dialog(dialog_id, operator)
        if not dialog["unread_count"]:
            return {"ok": True}
        await db.clear_unread(dialog_id)
        updated = await db.get_dialog(dialog_id)
        await ws.broadcast(
            {"type": "dialog_updated", "dialog": _fmt_dialog(updated)},
            service_id=dialog["service_id"],
        )
        return {"ok": True}

    @app.post("/api/dialogs/{dialog_id}/reply")
    async def reply(dialog_id: str, body: ReplyBody, operator: dict = Depends(require_auth)):
        dialog = await require_dialog(dialog_id, operator)

        # Use authenticated operator's name if body doesn't override it
        op_name = body.operator_name or operator["name"]
        msg_row = await db.save_message(
            dialog_id, "operator",
            body.text or None,
            file_type=body.file_type,
            file_url=body.file_url,
            operator_name=op_name,
        )
        preview = body.text or (f"[{body.file_type}]" if body.file_type else "—")
        await db.update_last_message(dialog_id, preview)
        if dialog["status"] == "new":
            await db.update_status(dialog_id, "in_progress")

        sid = dialog["service_id"]
        await n8n.send_manager_message(
            dialog["external_id"], dialog["chat_id"], dialog["service_slug"], body.text,
            file_url=body.file_url, file_type=body.file_type,
        )

        updated = await db.get_dialog(dialog_id)
        await ws.broadcast(
            {"type": "new_message", "dialog_id": dialog_id, "service_id": sid,
             "message": _fmt_message(msg_row)}, service_id=sid,
        )
        await ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)}, service_id=sid)
        return {"ok": True}

    @app.post("/api/dialogs/{dialog_id}/toggle_ai")
    async def toggle_ai(dialog_id: str, operator: dict = Depends(require_auth)):
        dialog = await require_dialog(dialog_id, operator)
        sid = dialog["service_id"]
        new_value = not dialog["ai_enabled"]
        await db.update_ai_enabled(dialog_id, new_value)
        await n8n.notify_ai_toggled(
            dialog["external_id"], dialog["chat_id"], dialog["service_slug"], new_value
        )
        updated = await db.get_dialog(dialog_id)
        await ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)}, service_id=sid)
        return {"ai_enabled": new_value}

    @app.post("/api/dialogs/{dialog_id}/handoff")
    async def handoff(dialog_id: str, body: HandoffBody = HandoffBody(), operator: dict = Depends(require_auth)):
        dialog = await require_dialog(dialog_id, operator)
        sid = dialog["service_id"]
        op_name = body.operator_name or operator["name"]
        msg_row = await db.save_message(dialog_id, "system", f"Диалог передан оператору {op_name}")
        await db.update_status(dialog_id, "in_progress")
        await db.update_operator_called(dialog_id, True)
        updated = await db.get_dialog(dialog_id)
        await ws.broadcast(
            {"type": "new_message", "dialog_id": dialog_id, "service_id": sid,
             "message": _fmt_message(msg_row)}, service_id=sid,
        )
        await ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)}, service_id=sid)
        username = updated.get("user_username") or dialog["external_id"]
        service = await db.get_service(sid)
        await n8n.schedule_notify(
            "operator_called", service, {"dialog_id": dialog["external_id"], "username": username}
        )
        return {"ok": True}

    @app.post("/api/dialogs/{dialog_id}/close")
    async def close_dialog(dialog_id: str, operator: dict = Depends(require_auth)):
        dialog = await require_dialog(dialog_id, operator)
        sid = dialog["service_id"]
        msg_row = await db.save_message(dialog_id, "system", "Диалог закрыт оператором")
        await db.update_status(dialog_id, "closed")
        await db.update_operator_called(dialog_id, False)
        updated = await db.get_dialog(dialog_id)
        await ws.broadcast(
            {"type": "new_message", "dialog_id": dialog_id, "service_id": sid,
             "message": _fmt_message(msg_row)}, service_id=sid,
        )
        await ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)}, service_id=sid)
        await n8n.notify_dialog_closed(
            dialog["external_id"], dialog["chat_id"], dialog["service_slug"], operator["name"]
        )
        if chat_client:
            asyncio.create_task(_summarize_dialog_bg(dialog_id))
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

    @app.post("/api/dialogs/{dialog_id}/billing/{action}")
    async def billing_action(dialog_id: str, action: str, body: dict = Body(default={}), operator: dict = Depends(require_auth)):
        if action not in ("renew", "buy_traffic", "reset_key"):
            raise HTTPException(400, f"Unknown action: {action}")
        dialog = await require_dialog(dialog_id, operator)
        # The billing API lives outside the panel and knows dialogs by the id
        # n8n assigned them, not by our composite key.
        result = await billing.execute(
            action, dialog["chat_id"], dialog["external_id"], params=body
        )
        if not result.ok:
            raise HTTPException(502, result.message)
        return {"ok": True, "message": result.message}

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

    # ── Servers ───────────────────────────────────────────────────────────────

    @app.get("/api/servers")
    async def get_servers(operator: dict = Depends(require_auth)):
        snapshot = server_monitor.get_snapshot()
        snapshot["is_stub"] = isinstance(server_monitor, StubServerMonitor)
        return snapshot

    # ── Statistics ────────────────────────────────────────────────────────────

    @app.get("/api/stats")
    async def get_stats(days: int = 14, service: str = "", operator: dict = Depends(require_auth)):
        require_admin(operator)
        if service:
            service_ids = [(await require_service(service, operator))["id"]]
        else:
            service_ids = await allowed_service_ids(operator)
        return await db.get_stats(days, service_ids)

    # ── Operators ─────────────────────────────────────────────────────────────

    @app.get("/api/operators")
    async def get_operators(operator: dict = Depends(require_auth)):
        by_op = await db.get_service_ids_by_operator()
        return [_fmt_operator(op, by_op.get(op["id"], [])) for op in await db.get_operators()]

    @app.get("/api/operators/me/notifications")
    async def get_my_notif_prefs(operator: dict = Depends(require_auth)):
        return _fmt_operator(operator)["notifPrefs"]

    @app.put("/api/operators/me/notifications")
    async def save_my_notif_prefs(body: NotifPrefsBody, operator: dict = Depends(require_auth)):
        await db.update_operator_notif_prefs(operator["id"], body.model_dump())
        return {"ok": True}

    @app.post("/api/operators")
    async def create_operator(body: OperatorBody, operator: dict = Depends(require_auth)):
        require_admin(operator)
        op = await db.create_operator(body.name, body.tg, body.role, tg_id=body.tg_id)
        if body.password:
            if len(body.password) < 6:
                raise HTTPException(400, "Password must be at least 6 characters")
            await db.set_password(op["id"], hash_password(body.password))
        if body.service_ids is not None:
            await db.set_operator_services(op["id"], body.service_ids)
        return _fmt_operator(op, await db.get_operator_service_ids(op["id"]))

    @app.put("/api/operators/{op_id}")
    async def update_operator(op_id: int, body: OperatorBody, operator: dict = Depends(require_auth)):
        require_admin(operator)
        result = await db.update_operator(op_id, body.name, body.tg, body.role, tg_id=body.tg_id)
        if not result:
            raise HTTPException(404)
        if body.service_ids is not None:
            await db.set_operator_services(op_id, body.service_ids)
        return _fmt_operator(result, await db.get_operator_service_ids(op_id))

    @app.put("/api/operators/{op_id}/services")
    async def set_operator_services(
        op_id: int, body: OperatorServicesBody, operator: dict = Depends(require_auth),
    ):
        """Assign the VPN services this operator is allowed to answer for."""
        require_admin(operator)
        target = await db.get_operator(op_id)
        if not target:
            raise HTTPException(404)
        known = {s["id"] for s in await db.get_services()}
        unknown = [sid for sid in body.service_ids if sid not in known]
        if unknown:
            raise HTTPException(400, f"Unknown service ids: {unknown}")
        await db.set_operator_services(op_id, body.service_ids)
        return _fmt_operator(target, await db.get_operator_service_ids(op_id))

    @app.delete("/api/operators/{op_id}")
    async def delete_operator(op_id: int, operator: dict = Depends(require_auth)):
        require_admin(operator)
        if op_id == operator["id"]:
            raise HTTPException(400, "Cannot delete yourself")
        ok = await db.delete_operator(op_id)
        if not ok:
            raise HTTPException(404)
        return {"ok": True}

    # ── Settings: AI ──────────────────────────────────────────────────────────

    @app.get("/api/settings/ai")
    async def get_ai_settings(service: str, operator: dict = Depends(require_auth)):
        svc = await require_service(service, operator)
        return await db.get_service_setting_json(svc["id"], "ai_settings", _AI_DEFAULTS)

    @app.put("/api/settings/ai")
    async def save_ai_settings(body: AISettingsBody, service: str, operator: dict = Depends(require_auth)):
        require_admin(operator)
        svc = await require_service(service, operator)
        data = body.model_dump()
        await db.set_service_setting_json(svc["id"], "ai_settings", data)
        # For n8n: append [HANDOFF] instruction when handoff is enabled
        n8n_data = dict(data)
        if data.get("handoff_enabled"):
            n8n_data["prompt"] = (data["prompt"] or "").rstrip() + (
                "\n\nЕсли вопрос сложный, ты не уверен в ответе или пользователь просит живого оператора — "
                "добавь [HANDOFF] в самое начало своего ответа. "
                "Пример: «[HANDOFF] Передаю вас оператору, он скоро ответит.» "
                "Без [HANDOFF] — отвечай самостоятельно."
            )
        await n8n.push_ai_settings(svc["slug"], n8n_data)
        return {"ok": True}

    # ── Settings: Schedule ────────────────────────────────────────────────────

    @app.get("/api/settings/schedule")
    async def get_schedule(service: str, operator: dict = Depends(require_auth)):
        svc = await require_service(service, operator)
        return await db.get_service_setting_json(svc["id"], "schedule", _SCHEDULE_DEFAULTS)

    @app.put("/api/settings/schedule")
    async def save_schedule(body: ScheduleBody, service: str, operator: dict = Depends(require_auth)):
        require_admin(operator)
        svc = await require_service(service, operator)
        await db.set_service_setting_json(svc["id"], "schedule", body.schedule)
        await n8n.push_schedule(svc["slug"], body.schedule)
        return {"ok": True}

    # ── Knowledge Base ────────────────────────────────────────────────────────

    @app.get("/api/kb")
    async def get_kb(service: str, operator: dict = Depends(require_auth)):
        svc = await require_service(service, operator)
        articles = await db.get_kb_articles(svc["id"])
        for a in articles:
            try:
                a["keywords"] = json.loads(a["keywords"])
            except Exception:
                a["keywords"] = []
        return articles

    @app.post("/api/kb/upload")
    async def upload_kb(service: str, file: UploadFile = File(...), operator: dict = Depends(require_auth)):
        require_admin(operator)
        svc = await require_service(service, operator)
        if not settings.OPENAI_API_KEY:
            raise HTTPException(400, "OPENAI_API_KEY is required for embeddings")
        if not chat_client:
            raise HTTPException(400, "AI-провайдер не настроен — загрузка базы знаний недоступна")
        if not file.filename.endswith((".txt", ".md")):
            raise HTTPException(400, "Only .txt and .md files are supported")
        text = (await file.read()).decode("utf-8", errors="ignore")
        if not text.strip():
            raise HTTPException(400, "File is empty")
        chunks = await process_document(
            text, chat_client, settings.OPENAI_API_KEY, settings.QDRANT_URL, svc["slug"],
        )
        for c in chunks:
            await db.save_kb_article(
                c["id"], c["title"], c["category"],
                json.dumps(c["keywords"], ensure_ascii=False),
                c["content"], svc["id"],
            )
        return {"chunks_created": len(chunks), "ids": [c["id"] for c in chunks]}

    @app.delete("/api/kb/{article_id:path}")
    async def delete_kb_article(article_id: str, operator: dict = Depends(require_auth)):
        require_admin(operator)
        article = await db.get_kb_article(article_id)
        if not article:
            raise HTTPException(404)
        svc = await db.get_service(article["service_id"])
        await db.delete_kb_article(article_id)
        if svc:
            await delete_from_qdrant(
                article_id, settings.QDRANT_URL, kb_collection_name(svc["slug"])
            )
        return {"ok": True}

    # ── WebSocket ─────────────────────────────────────────────────────────────

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket, token: str = ""):
        op_id = decode_token(token, settings.SECRET_KEY)
        if not op_id:
            await websocket.close(code=4001)
            return
        operator = await db.get_operator(op_id)
        if not operator:
            await websocket.close(code=4001)
            return
        went_online = await ws.connect(websocket, op_id, await allowed_service_ids(operator))
        if went_online:
            await db.set_operator_online(op_id, True)
            await ws.broadcast({"type": "operator_status", "op_id": op_id, "online": True})
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            departed_id, went_offline = ws.disconnect(websocket)
            if went_offline and departed_id:
                await db.set_operator_online(departed_id, False)
                await ws.broadcast({"type": "operator_status", "op_id": departed_id, "online": False})

    return app
