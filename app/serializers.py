"""Row → frontend-shape serializers shared by web_server, routing and consumers."""
import json
from datetime import datetime, timezone

from app.database import avatar_color, make_initials

NOTIF_PREFS_DEFAULT = {"new_dialog": True, "operator_called": True, "server_down": True, "sound_enabled": True}


def fmt_time(dt: datetime) -> str:
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


def fmt_dialog(row: dict, tickets: list = None) -> dict:
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
        "time": fmt_time(row.get("last_message_time")),
        "assignedOperator": row.get("assigned_operator"),
        "updatedAt": row["updated_at"].isoformat() if row.get("updated_at") else "",
        "rating": row.get("rating"),
        "notes": row.get("user_notes") or "",
        "photoUrl": row.get("user_photo_url") or None,
        "waitingReason": row.get("waiting_reason"),
        "slaSeconds": row.get("sla_seconds_total") or 0,
        "slaStartedAt": row["sla_started_at"].isoformat() if row.get("sla_started_at") else None,
        "returnRequested": bool(row.get("return_requested_at")),
        "tickets": tickets or [],
    }


def fmt_message(row: dict) -> dict:
    file_id = row.get("file_id")
    file_url = row.get("file_url")
    # handle legacy records where n8n put the URL into file_id
    if not file_url and file_id and str(file_id).startswith("http"):
        file_url, file_id = file_id, None
    created = row.get("created_at")
    if created and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return {
        "id": row["id"],
        "kind": row["kind"],
        "text": row.get("text") or "",
        "fileId": file_id,
        "fileType": row.get("file_type"),
        "fileUrl": file_url,
        "operator": row.get("operator_name"),
        "time": fmt_time(row.get("created_at")),
        "createdAt": created.isoformat() if created else "",
        "deliveryStatus": row.get("delivery_status"),
        "deliveryError": row.get("delivery_error"),
    }


def fmt_operator(op: dict) -> dict:
    raw_prefs = op.get("notif_prefs")
    notif_prefs = {**NOTIF_PREFS_DEFAULT, **(json.loads(raw_prefs) if raw_prefs else {})}
    return {
        "id": op["id"],
        "name": op["name"],
        "tg": op["tg"],
        "tgId": op.get("tg_id"),
        "role": op["role"],
        "initials": op.get("initials") or make_initials(op["name"]),
        "color": op.get("color") or "#4F8EF7",
        "online": op.get("online", False),
        "paused": op.get("paused", False),
        "notifPrefs": notif_prefs,
    }
