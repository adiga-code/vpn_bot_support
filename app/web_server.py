import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.auth import create_token, decode_token, hash_password, verify_password
from app.billing import BillingProvider
from app.config import Settings
from app.database import DatabaseManager, avatar_color, make_initials
from app.kb import delete_from_qdrant, process_document
from app.n8n_client import N8NClient
from app.servers import ServerMonitor
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
}

_NOTIF_DEFAULTS = {"new_dialog": True, "operator_called": True, "server_down": True}

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
    name = row.get("user_name") or did
    username = row.get("user_username") or f"@{row['chat_id']}"
    return {
        "id": did,
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
    return {
        "id": row["id"],
        "kind": row["kind"],
        "text": row.get("text") or "",
        "fileId": row.get("file_id"),
        "fileType": row.get("file_type"),
        "fileUrl": row.get("file_url"),
        "operator": row.get("operator_name"),
        "time": _fmt_time(row.get("created_at")),
    }


def _fmt_operator(op: dict) -> dict:
    return {
        "id": op["id"],
        "name": op["name"],
        "tg": op["tg"],
        "role": op["role"],
        "initials": op.get("initials") or make_initials(op["name"]),
        "color": op.get("color") or "#4F8EF7",
        "online": op.get("online", False),
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
    role: str = "agent"
    password: str = ""

class AISettingsBody(BaseModel):
    prompt: str
    temperature: float
    auto_reply: bool
    handoff_enabled: bool

class ScheduleBody(BaseModel):
    schedule: dict

class NotificationsBody(BaseModel):
    new_dialog:      bool = True
    operator_called: bool = True
    server_down:     bool = True


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

    if _STATIC.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

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
                "title": t["last_message_text"] or "Диалог",
                "date": _fmt_time(t["updated_at"]),
                "solved": True,
            }
            for t in tickets
        ])

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

        await n8n.send_manager_message(
            dialog_id, dialog["chat_id"], body.text,
            file_url=body.file_url, file_type=body.file_type,
        )

        updated = await db.get_dialog(dialog_id)
        await ws.broadcast({"type": "new_message", "dialog_id": dialog_id, "message": _fmt_message(msg_row)})
        await ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)})
        return {"ok": True}

    @app.post("/api/dialogs/{dialog_id}/toggle_ai")
    async def toggle_ai(dialog_id: str, operator: dict = Depends(require_auth)):
        dialog = await db.get_dialog(dialog_id)
        if not dialog:
            raise HTTPException(404)
        new_value = not dialog["ai_enabled"]
        await db.update_ai_enabled(dialog_id, new_value)
        await n8n.notify_ai_toggled(dialog_id, dialog["chat_id"], new_value)
        updated = await db.get_dialog(dialog_id)
        await ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)})
        return {"ai_enabled": new_value}

    @app.post("/api/dialogs/{dialog_id}/handoff")
    async def handoff(dialog_id: str, body: HandoffBody = HandoffBody(), operator: dict = Depends(require_auth)):
        dialog = await db.get_dialog(dialog_id)
        if not dialog:
            raise HTTPException(404)
        op_name = body.operator_name or operator["name"]
        msg_row = await db.save_message(dialog_id, "system", f"Диалог передан оператору {op_name}")
        await db.update_status(dialog_id, "in_progress")
        await db.update_operator_called(dialog_id, True)
        updated = await db.get_dialog(dialog_id)
        await ws.broadcast({"type": "new_message", "dialog_id": dialog_id, "message": _fmt_message(msg_row)})
        await ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)})
        notif = await db.get_setting_json("notifications", _NOTIF_DEFAULTS)
        if notif.get("operator_called"):
            username = updated.get("user_username") or dialog_id
            await n8n.notify_event("operator_called", {"dialog_id": dialog_id, "username": username})
        return {"ok": True}

    @app.post("/api/dialogs/{dialog_id}/close")
    async def close_dialog(dialog_id: str, operator: dict = Depends(require_auth)):
        dialog = await db.get_dialog(dialog_id)
        if not dialog:
            raise HTTPException(404)
        msg_row = await db.save_message(dialog_id, "system", "Диалог закрыт оператором")
        await db.update_status(dialog_id, "closed")
        await db.update_operator_called(dialog_id, False)
        updated = await db.get_dialog(dialog_id)
        await ws.broadcast({"type": "new_message", "dialog_id": dialog_id, "message": _fmt_message(msg_row)})
        await ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)})
        return {"ok": True}

    @app.post("/api/dialogs/{dialog_id}/billing/{action}")
    async def billing_action(dialog_id: str, action: str, operator: dict = Depends(require_auth)):
        if action not in ("renew", "buy_traffic", "reset_key"):
            raise HTTPException(400, f"Unknown action: {action}")
        dialog = await db.get_dialog(dialog_id)
        if not dialog:
            raise HTTPException(404)
        result = await billing.execute(action, dialog["chat_id"], dialog_id)
        if not result.ok:
            raise HTTPException(502, result.message)
        return {"ok": True, "message": result.message}

    # ── File upload ───────────────────────────────────────────────────────────

    @app.post("/api/upload")
    async def upload_file(file: UploadFile = File(...), operator: dict = Depends(require_auth)):
        ext = Path(file.filename).suffix if file.filename else ""
        filename = f"{uuid.uuid4().hex}{ext}"
        dest = uploads / filename
        content = await file.read()
        dest.write_bytes(content)
        return {"url": f"/api/files/{filename}", "filename": filename}

    # ── Servers ───────────────────────────────────────────────────────────────

    @app.get("/api/servers")
    async def get_servers(operator: dict = Depends(require_auth)):
        return server_monitor.get_snapshot()

    # ── Statistics ────────────────────────────────────────────────────────────

    @app.get("/api/stats")
    async def get_stats(days: int = 14, operator: dict = Depends(require_auth)):
        return await db.get_stats(days)

    # ── Operators ─────────────────────────────────────────────────────────────

    @app.get("/api/operators")
    async def get_operators(operator: dict = Depends(require_auth)):
        return await db.get_operators()

    @app.post("/api/operators")
    async def create_operator(body: OperatorBody, operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        op = await db.create_operator(body.name, body.tg, body.role)
        if body.password:
            if len(body.password) < 6:
                raise HTTPException(400, "Password must be at least 6 characters")
            await db.set_password(op["id"], hash_password(body.password))
        return op

    @app.put("/api/operators/{op_id}")
    async def update_operator(op_id: int, body: OperatorBody, operator: dict = Depends(require_auth)):
        if operator["role"] != "admin":
            raise HTTPException(403, "Admin only")
        result = await db.update_operator(op_id, body.name, body.tg, body.role)
        if not result:
            raise HTTPException(404)
        return result

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

    @app.put("/api/settings/ai")
    async def save_ai_settings(body: AISettingsBody, operator: dict = Depends(require_auth)):
        data = body.model_dump()
        await db.set_setting_json("ai_settings", data)
        await n8n.redis.set("vpn_bot:ai_settings", json.dumps(data))
        return {"ok": True}

    # ── Settings: Schedule ────────────────────────────────────────────────────

    @app.get("/api/settings/schedule")
    async def get_schedule(operator: dict = Depends(require_auth)):
        return await db.get_setting_json("schedule", _SCHEDULE_DEFAULTS)

    @app.put("/api/settings/schedule")
    async def save_schedule(body: ScheduleBody, operator: dict = Depends(require_auth)):
        await db.set_setting_json("schedule", body.schedule)
        await n8n.redis.set("vpn_bot:schedule", json.dumps(body.schedule))
        return {"ok": True}

    # ── Settings: Notifications ───────────────────────────────────────────────

    @app.get("/api/settings/notifications")
    async def get_notifications(operator: dict = Depends(require_auth)):
        return await db.get_setting_json("notifications", _NOTIF_DEFAULTS)

    @app.put("/api/settings/notifications")
    async def save_notifications(body: NotificationsBody, operator: dict = Depends(require_auth)):
        await db.set_setting_json("notifications", body.model_dump())
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
        if not settings.OPENAI_API_KEY:
            raise HTTPException(400, "OPENAI_API_KEY not configured")
        if not file.filename.endswith((".txt", ".md")):
            raise HTTPException(400, "Only .txt and .md files are supported")
        text = (await file.read()).decode("utf-8", errors="ignore")
        if not text.strip():
            raise HTTPException(400, "File is empty")
        chunks = await process_document(text, settings.OPENAI_API_KEY, settings.QDRANT_URL)
        for c in chunks:
            await db.save_kb_article(
                c["id"], c["title"], c["category"],
                json.dumps(c["keywords"], ensure_ascii=False),
                c["content"],
            )
        return {"chunks_created": len(chunks), "ids": [c["id"] for c in chunks]}

    @app.delete("/api/kb/{article_id}")
    async def delete_kb_article(article_id: str, operator: dict = Depends(require_auth)):
        ok = await db.delete_kb_article(article_id)
        if not ok:
            raise HTTPException(404)
        await delete_from_qdrant(article_id, settings.QDRANT_URL)
        return {"ok": True}

    # ── WebSocket ─────────────────────────────────────────────────────────────

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket, token: str = ""):
        op_id = decode_token(token, settings.SECRET_KEY)
        if not op_id:
            await websocket.close(code=4001)
            return
        await ws.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            ws.disconnect(websocket)

    return app
