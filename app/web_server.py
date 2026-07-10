import asyncio
import json
import uuid
from pathlib import Path
from typing import Optional

from fastapi import Body, Depends, FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.ai_client import make_chat_client
from app.auth import create_token, decode_token, hash_password, verify_password
from app.billing import BillingProvider
from app.config import Settings
from app.database import DatabaseManager
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


# ── App factory ───────────────────────────────────────────────────────────────

def build_app(
    settings: Settings,
    db: DatabaseManager,
    ws: WebSocketManager,
    n8n: N8NClient,
    routing: RoutingEngine,
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
    async def get_dialogs(operator: dict = Depends(require_auth)):
        rows = await db.get_all_dialogs()
        return [_fmt_dialog(r) for r in rows]

    @app.get("/api/dialogs/{dialog_id}")
    async def get_dialog(dialog_id: str, operator: dict = Depends(require_auth)):
        row = await db.get_dialog(dialog_id)
        if not row:
            raise HTTPException(404)
        tickets = await db.get_dialog_history(row["chat_id"], dialog_id)
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
        row = await db.get_dialog(dialog_id)
        if not row:
            raise HTTPException(404)
        history = await db.get_dialog_history(row["chat_id"], dialog_id)
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
        await db.clear_unread(dialog_id)
        rows = await db.get_messages(dialog_id)
        return [_fmt_message(r) for r in rows]

    @app.post("/api/dialogs/{dialog_id}/reply")
    async def reply(dialog_id: str, body: ReplyBody, operator: dict = Depends(require_auth)):
        dialog = await db.get_dialog(dialog_id)
        if not dialog:
            raise HTTPException(404)

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
            message_id=msg_row["id"],
        )
        if not delivered:
            await db.update_message_delivery(msg_row["id"], "failed", "Очередь недоступна")
        await db.clear_unread(dialog_id)

        await ws.broadcast({"type": "new_message", "dialog_id": dialog_id, "message": _fmt_message(msg_row)})
        # Scenario 2: the answered ticket moves to waiting («ждём ответ»),
        # SLA pauses, the slot frees up (broadcasts the updated dialog).
        await routing.on_operator_reply(dialog, op_name)
        return {"ok": True, "delivered": delivered}

    @app.post("/api/dialogs/{dialog_id}/comment")
    async def add_comment(dialog_id: str, body: CommentBody, operator: dict = Depends(require_auth)):
        dialog = await db.get_dialog(dialog_id)
        if not dialog:
            raise HTTPException(404)
        if not body.text.strip():
            raise HTTPException(400, "Пустой комментарий")
        msg_row = await db.save_message(
            dialog_id, "comment", body.text.strip(), operator_name=operator["name"]
        )
        await ws.broadcast({"type": "new_message", "dialog_id": dialog_id, "message": _fmt_message(msg_row)})
        return {"ok": True}

    @app.put("/api/dialogs/{dialog_id}/notes")
    async def update_notes(dialog_id: str, body: NotesBody, operator: dict = Depends(require_auth)):
        dialog = await db.get_dialog(dialog_id)
        if not dialog:
            raise HTTPException(404)
        await db.pool.execute(
            "UPDATE dialogs SET user_notes=$1 WHERE dialog_id=$2", body.text, dialog_id
        )
        updated = await db.get_dialog(dialog_id)
        await ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)})
        return {"ok": True}

    @app.post("/api/dialogs/{dialog_id}/dismiss_called")
    async def dismiss_called(dialog_id: str, operator: dict = Depends(require_auth)):
        dialog = await db.get_dialog(dialog_id)
        if not dialog:
            raise HTTPException(404)
        await db.pool.execute(
            "UPDATE dialogs SET operator_called=FALSE WHERE dialog_id=$1", dialog_id
        )
        updated = await db.get_dialog(dialog_id)
        await ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)})
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
            await ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)})
        return {"ok": True}

    @app.post("/api/dialogs/{dialog_id}/toggle_ai")
    async def toggle_ai(dialog_id: str, operator: dict = Depends(require_auth)):
        dialog = await db.get_dialog(dialog_id)
        if not dialog:
            raise HTTPException(404)
        new_value = not dialog["ai_enabled"]
        await db.update_ai_enabled(dialog_id, new_value)
        await db.sync_n8n_dialog_ai_status(dialog["chat_id"], new_value)
        await n8n.notify_ai_toggled(dialog_id, dialog["chat_id"], new_value)
        # Keep the status model coherent: AI back on while queued → «ИИ» section;
        # AI off while unattended in «ИИ» → escalate to humans.
        await routing.on_ai_toggled(dialog_id, new_value)
        updated = await db.get_dialog(dialog_id)
        await ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)})
        return {"ai_enabled": new_value}

    @app.post("/api/dialogs/{dialog_id}/handoff")
    async def handoff(dialog_id: str, body: HandoffBody = HandoffBody(), operator: dict = Depends(require_auth)):
        dialog = await db.get_dialog(dialog_id)
        if not dialog:
            raise HTTPException(404)
        op_name = body.operator_name or operator["name"] or "Оператор"
        updated = await routing.take_in_work(dialog_id, op_name)
        if not updated:
            raise HTTPException(400, "Dialog is closed")
        return {"ok": True}

    @app.post("/api/dialogs/{dialog_id}/reopen-closed")
    async def reopen_closed_dialog(dialog_id: str, operator: dict = Depends(require_auth)):
        dialog = await db.get_dialog(dialog_id)
        if not dialog:
            raise HTTPException(404)
        if dialog["status"] != "closed":
            raise HTTPException(400, "Dialog is not closed")
        active = await db.get_active_dialog_by_chat_id(dialog["chat_id"], exclude_dialog_id=dialog_id)
        if active:
            return JSONResponse(status_code=409, content={"active_dialog_id": active["dialog_id"]})
        # → queue, unassigned; AI stays off (the ticket had been escalated)
        await routing.reopen_closed(dialog_id, dialog["chat_id"])
        return {"ok": True}

    @app.post("/api/dialogs/{dialog_id}/reopen")
    async def reopen_dialog(dialog_id: str, operator: dict = Depends(require_auth)):
        dialog = await db.get_dialog(dialog_id)
        if not dialog:
            raise HTTPException(404)
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
        dialog = await db.get_dialog(dialog_id)
        if not dialog:
            raise HTTPException(404)
        try:
            await routing.set_waiting_manual(dialog_id, operator["name"])
        except ValueError:
            raise HTTPException(400, "Only in_progress tickets can be paused")
        return {"ok": True}

    @app.post("/api/dialogs/{dialog_id}/transfer")
    async def transfer_dialog(dialog_id: str, body: TransferBody, operator: dict = Depends(require_auth)):
        dialog = await db.get_dialog(dialog_id)
        if not dialog:
            raise HTTPException(404)
        if operator["role"] != "admin" and dialog.get("assigned_operator") != operator["name"]:
            raise HTTPException(403, "Can only transfer your own dialogs")
        target = await db.get_operator_by_name(body.operator_name)
        if not target:
            raise HTTPException(404, "Target operator not found")
        await routing.transfer(dialog_id, body.operator_name)
        return {"ok": True}

    @app.post("/api/dialogs/{dialog_id}/close")
    async def close_dialog(dialog_id: str, operator: dict = Depends(require_auth)):
        dialog = await db.get_dialog(dialog_id)
        if not dialog:
            raise HTTPException(404)
        # Transition + system message + broadcasts + n8n sync + queue drain
        await routing.close(dialog_id, dialog["chat_id"], operator["name"])
        if chat_client:
            asyncio.create_task(_summarize_dialog_bg(dialog_id))
        automation = await db.get_setting_json("automation", _AUTOMATION_DEFAULTS)
        if automation.get("close_message_enabled") and automation.get("close_message_text"):
            asyncio.create_task(n8n.send_to_user(dialog["chat_id"], automation["close_message_text"]))
        if automation.get("rating_enabled"):
            rating_text = automation.get("rating_message_text") or "Оцените качество поддержки:"
            asyncio.create_task(n8n.send_rating_request(dialog["chat_id"], dialog_id, rating_text))
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
        dialog = await db.get_dialog(dialog_id)
        if not dialog:
            raise HTTPException(404)
        result = await billing.execute(action, dialog["chat_id"], dialog_id, params=body)
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
    async def get_stats(days: int = 14, operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        return await db.get_stats(days)

    @app.get("/api/stats/times")
    async def get_time_stats(days: int = 30, operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        return await db.get_time_stats(days)

    # ── Operators ─────────────────────────────────────────────────────────────

    @app.get("/api/operators")
    async def get_operators(operator: dict = Depends(require_auth)):
        return [_fmt_operator(op) for op in await db.get_operators()]

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
        return _fmt_operator(op)

    @app.put("/api/operators/{op_id}")
    async def update_operator(op_id: int, body: OperatorBody, operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        result = await db.update_operator(op_id, body.name, body.tg, body.role, tg_id=body.tg_id)
        if not result:
            raise HTTPException(404)
        return _fmt_operator(result)

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
    async def get_ai_settings(operator: dict = Depends(require_auth)):
        return await db.get_setting_json("ai_settings", _AI_DEFAULTS)

    async def _sync_ai_settings_to_redis(ai: dict):
        """Push AI settings to the Redis copy the n8n agent reads, appending
        the escalation instruction while auto-handoff is on. EVERY endpoint
        that rewrites vpn_bot:ai_settings must go through here — writing the
        raw prompt silently kills auto-handoff (the model stops being told
        how to escalate)."""
        n8n_data = dict(ai)
        if ai.get("handoff_enabled"):
            n8n_data["prompt"] = (ai.get("prompt") or "").rstrip() + (
                "\n\nЕсли вопрос сложный, ты не уверен в ответе или пользователь просит живого оператора — "
                "поставь handoff=true и кратко укажи причину в поле reason, "
                "а в поле answer обычным текстом предупреди клиента, что передаёшь диалог оператору. "
                "Иначе всегда handoff=false."
            )
        await n8n.redis.set("vpn_bot:ai_settings", json.dumps(n8n_data, ensure_ascii=False))

    @app.put("/api/settings/ai")
    async def save_ai_settings(body: AISettingsBody, operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        data = body.model_dump()
        await db.set_setting_json("ai_settings", data)
        await _sync_ai_settings_to_redis(data)
        return {"ok": True}

    # ── Settings: Schedule ────────────────────────────────────────────────────

    @app.get("/api/settings/schedule")
    async def get_schedule(operator: dict = Depends(require_auth)):
        return await db.get_setting_json("schedule", _SCHEDULE_DEFAULTS)

    @app.put("/api/settings/schedule")
    async def save_schedule(body: ScheduleBody, operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        await db.set_setting_json("schedule", body.schedule)
        await n8n.redis.set("vpn_bot:schedule", json.dumps(body.schedule, ensure_ascii=False))
        return {"ok": True}

    # ── Knowledge Base ────────────────────────────────────────────────────────

    @app.get("/api/kb")
    async def get_kb(operator: dict = Depends(require_auth)):
        articles = await db.get_kb_articles()
        for a in articles:
            try:
                a["keywords"] = json.loads(a["keywords"])
            except Exception:
                a["keywords"] = []
        return articles

    @app.post("/api/kb/upload")
    async def upload_kb(file: UploadFile = File(...), operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        if not settings.OPENAI_API_KEY:
            raise HTTPException(400, "OPENAI_API_KEY is required for embeddings")
        if not file.filename.endswith((".txt", ".md")):
            raise HTTPException(400, "Only .txt and .md files are supported")
        text = (await file.read()).decode("utf-8", errors="ignore")
        if not text.strip():
            raise HTTPException(400, "File is empty")
        chunks = await process_document(text, chat_client, settings.OPENAI_API_KEY, settings.QDRANT_URL)
        for c in chunks:
            await db.save_kb_article(
                c["id"], c["title"], c["category"],
                json.dumps(c["keywords"], ensure_ascii=False),
                c["content"],
            )
        return {"chunks_created": len(chunks), "ids": [c["id"] for c in chunks]}

    @app.delete("/api/kb")
    async def reset_kb_all(operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        await db.reset_kb()
        from qdrant_client import AsyncQdrantClient
        from app.kb import ensure_collection
        client = AsyncQdrantClient(url=settings.QDRANT_URL)
        try:
            await client.delete_collection("kb")
        except Exception:
            pass
        finally:
            await client.close()
        await ensure_collection(settings.QDRANT_URL)
        return {"ok": True}

    @app.delete("/api/kb/{article_id}")
    async def delete_kb_article(article_id: str, operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        ok = await db.delete_kb_article(article_id)
        if not ok:
            raise HTTPException(404)
        await delete_from_qdrant(article_id, settings.QDRANT_URL)
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
    async def get_automation(operator: dict = Depends(require_auth)):
        stored = await db.get_setting_json("automation", None) or {}
        # merge so settings saved before new keys existed still expose defaults
        return {**_AUTOMATION_DEFAULTS, **stored}

    @app.put("/api/settings/automation")
    async def save_automation(body: AutomationSettingsBody, operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        data = body.model_dump()
        await db.set_setting_json("automation", data)
        # Синхронизировать auto_handoff_enabled → ai_settings для консьюмеров
        ai = await db.get_setting_json("ai_settings", _AI_DEFAULTS)
        ai["handoff_enabled"] = data["auto_handoff_enabled"]
        await db.set_setting_json("ai_settings", ai)
        # через общий хелпер — иначе инструкция эскалации пропадёт из промпта
        await _sync_ai_settings_to_redis(ai)
        return {"ok": True}

    # ── Broadcast ─────────────────────────────────────────────────────────────

    @app.post("/api/broadcast")
    async def broadcast_msg(body: BroadcastBody, operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        if not body.text.strip():
            raise HTTPException(400, "Текст не может быть пустым")
        lock_key = "vpn_bot:broadcast_lock"
        if await n8n.redis.get(lock_key):
            raise HTTPException(429, "Рассылка уже выполняется")
        await n8n.redis.set(lock_key, "1", ex=30)
        chat_ids = await db.get_all_chat_ids()
        sent = 0
        failed = 0
        try:
            for cid in chat_ids:
                ok = await n8n.send_to_user(cid, body.text)
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
    async def get_templates(operator: dict = Depends(require_auth)):
        return await db.get_templates()

    @app.post("/api/templates")
    async def create_template(body: TemplateBody, operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        if not body.title.strip() or not body.text.strip():
            raise HTTPException(400, "Название и текст обязательны")
        return await db.save_template(None, body.group_name.strip() or "Общие", body.title.strip(), body.text.strip())

    @app.put("/api/templates/{template_id}")
    async def update_template(template_id: int, body: TemplateBody, operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        row = await db.save_template(template_id, body.group_name.strip() or "Общие", body.title.strip(), body.text.strip())
        if not row:
            raise HTTPException(404)
        return row

    @app.delete("/api/templates/{template_id}")
    async def delete_template_ep(template_id: int, operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        ok = await db.delete_template(template_id)
        if not ok:
            raise HTTPException(404)
        return {"ok": True}

    @app.patch("/api/templates/group")
    async def rename_template_group(body: RenameGroupBody, operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        if not body.new_name.strip():
            raise HTTPException(400, "Название группы не может быть пустым")
        await db.rename_template_group(body.old_name.strip(), body.new_name.strip())
        return {"ok": True}

    # ── WebSocket ─────────────────────────────────────────────────────────────

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket, token: str = ""):
        op_id = decode_token(token, settings.SECRET_KEY)
        if not op_id:
            await websocket.close(code=4001)
            return
        went_online = await ws.connect(websocket, op_id)
        if went_online:
            op = await db.get_operator(op_id)
            await db.set_operator_online(op_id, True)
            # back within the grace period — cancel the offline timer
            await db.set_operator_offline_since(op_id, False)
            await ws.broadcast({"type": "operator_status", "op_id": op_id, "online": True, "paused": op.get("paused", False) if op else False})
            if op:
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
                await ws.broadcast({"type": "operator_status", "op_id": departed_id, "online": False, "paused": False})

    return app
