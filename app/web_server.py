from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import Settings
from app.database import DatabaseManager, avatar_color, make_initials
from app.n8n_client import N8NClient
from app.ws_manager import WebSocketManager

_STATIC = Path(__file__).parent / "static"


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


def _fmt_dialog(row: dict) -> dict:
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
        "tickets": [],
    }


def _fmt_message(row: dict) -> dict:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "text": row.get("text") or "",
        "fileId": row.get("file_id"),
        "fileType": row.get("file_type"),
        "operator": row.get("operator_name"),
        "time": _fmt_time(row.get("created_at")),
    }


class ReplyBody(BaseModel):
    text: str
    operator_name: str = "Оператор"


class HandoffBody(BaseModel):
    operator_name: str = "Оператор"


def build_app(
    settings: Settings,
    db: DatabaseManager,
    ws: WebSocketManager,
    n8n: N8NClient,
) -> FastAPI:
    app = FastAPI(title="VPN Helpdesk")

    # ── Static files ─────────────────────────────────────────────────────────
    if _STATIC.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

    @app.get("/")
    async def index():
        return FileResponse(_STATIC / "index.html")

    # ── Dialogs ───────────────────────────────────────────────────────────────
    @app.get("/api/dialogs")
    async def get_dialogs():
        rows = await db.get_all_dialogs()
        return [_fmt_dialog(r) for r in rows]

    @app.get("/api/dialogs/{dialog_id}/messages")
    async def get_messages(dialog_id: str):
        await db.clear_unread(dialog_id)
        rows = await db.get_messages(dialog_id)
        return [_fmt_message(r) for r in rows]

    @app.post("/api/dialogs/{dialog_id}/reply")
    async def reply(dialog_id: str, body: ReplyBody):
        dialog = await db.get_dialog(dialog_id)
        if not dialog:
            raise HTTPException(404, "Dialog not found")

        msg_row = await db.save_message(
            dialog_id, "operator", body.text, operator_name=body.operator_name
        )
        await db.update_last_message(dialog_id, body.text)
        if dialog["status"] == "new":
            await db.update_status(dialog_id, "in_progress")

        await n8n.send_manager_message(dialog_id, dialog["chat_id"], body.text)

        updated = await db.get_dialog(dialog_id)
        await ws.broadcast({"type": "new_message", "dialog_id": dialog_id, "message": _fmt_message(msg_row)})
        await ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)})
        return {"ok": True}

    @app.post("/api/dialogs/{dialog_id}/toggle_ai")
    async def toggle_ai(dialog_id: str):
        dialog = await db.get_dialog(dialog_id)
        if not dialog:
            raise HTTPException(404, "Dialog not found")

        result = await n8n.toggle_ai_status(dialog_id, dialog["chat_id"])
        if "error" in result:
            raise HTTPException(500, result["error"])

        new_state: bool = result["ai_enabled"]
        await db.update_ai_enabled(dialog_id, new_state)
        updated = await db.get_dialog(dialog_id)
        await ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)})
        return {"ai_enabled": new_state}

    @app.post("/api/dialogs/{dialog_id}/handoff")
    async def handoff(dialog_id: str, body: HandoffBody = HandoffBody()):
        dialog = await db.get_dialog(dialog_id)
        if not dialog:
            raise HTTPException(404, "Dialog not found")

        text = f"Диалог передан оператору {body.operator_name}"
        msg_row = await db.save_message(dialog_id, "system", text)
        await db.update_status(dialog_id, "in_progress")
        await db.update_operator_called(dialog_id, True)

        updated = await db.get_dialog(dialog_id)
        await ws.broadcast({"type": "new_message", "dialog_id": dialog_id, "message": _fmt_message(msg_row)})
        await ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)})
        return {"ok": True}

    @app.post("/api/dialogs/{dialog_id}/close")
    async def close_dialog(dialog_id: str):
        dialog = await db.get_dialog(dialog_id)
        if not dialog:
            raise HTTPException(404, "Dialog not found")

        msg_row = await db.save_message(dialog_id, "system", "Диалог закрыт оператором")
        await db.update_status(dialog_id, "closed")
        await db.update_operator_called(dialog_id, False)

        updated = await db.get_dialog(dialog_id)
        await ws.broadcast({"type": "new_message", "dialog_id": dialog_id, "message": _fmt_message(msg_row)})
        await ws.broadcast({"type": "dialog_updated", "dialog": _fmt_dialog(updated)})
        return {"ok": True}

    @app.post("/api/dialogs/{dialog_id}/billing/{action}")
    async def billing_action(dialog_id: str, action: str):
        if action not in ("renew", "buy_traffic", "reset_key"):
            raise HTTPException(400, f"Unknown billing action: {action}")
        dialog = await db.get_dialog(dialog_id)
        if not dialog:
            raise HTTPException(404, "Dialog not found")

        ok = await n8n.send_billing_action(dialog_id, dialog["chat_id"], action)
        return {"ok": ok}

    # ── WebSocket ─────────────────────────────────────────────────────────────
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await ws.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            ws.disconnect(websocket)

    return app
