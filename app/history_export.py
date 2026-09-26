"""Выгрузка старых переписок аккаунта поддержки в JSON.

Панель видит только то, что пришло после её подключения. Всё, что клиенты
писали раньше, лежит в самом аккаунте Telegram — его и выгружаем по MTProto,
той же сессией, что настроена для резервной отправки (app_id/app_hash и
StringSession в настройке `fallback_sender` сервиса).

Берутся только личные чаты с людьми: без ботов, групп, каналов, «Избранного»
и служебного 777000. Медиа не скачиваются — вместо них текстовая пометка
(«[фото]», «[файл: name.pdf]»): история нужна, чтобы понимать контекст, а
гигабайты вложений раздули бы файл и выгрузку.

Чатов могут быть тысячи, а Telegram отвечает FloodWait на слишком частые
запросы, поэтому выгрузка идёт фоновой задачей, а панель опрашивает прогресс.
Готовый файл лежит в `<UPLOADS_DIR>/exports/` — вне отдачи /api/files (там
только плоские имена), скачать его может только админ.

Формат файла — см. HISTORY_FORMAT и HistoryImporter.
"""
import asyncio
import json
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

from app.fallback_sender import TelethonSender, _install_hint
from app.redact import redact

HISTORY_FORMAT = "vpn-helpdesk-history/1"

# Служебные уведомления Telegram (коды входа и т. п.) — не клиент.
_TELEGRAM_SERVICE_ID = 777000


def _media_mark(msg) -> str:
    if getattr(msg, "photo", None):
        return "[фото]"
    if getattr(msg, "voice", None):
        return "[голосовое]"
    if getattr(msg, "video_note", None):
        return "[видеосообщение]"
    if getattr(msg, "video", None):
        return "[видео]"
    if getattr(msg, "sticker", None):
        return "[стикер]"
    if getattr(msg, "gif", None):
        return "[gif]"
    if getattr(msg, "audio", None):
        return "[аудио]"
    doc = getattr(msg, "document", None)
    if doc is not None:
        name = getattr(getattr(msg, "file", None), "name", None)
        return f"[файл: {name}]" if name else "[файл]"
    if getattr(msg, "contact", None):
        return "[контакт]"
    if getattr(msg, "geo", None):
        return "[геолокация]"
    if getattr(msg, "poll", None):
        return "[опрос]"
    if getattr(msg, "media", None) is not None:
        return "[вложение]"
    return ""


def message_to_json(msg) -> dict | None:
    """Сообщение Telethon → запись выгрузки; служебное или пустое — None."""
    if getattr(msg, "action", None) is not None:
        return None
    text = (getattr(msg, "message", None) or "").strip()
    mark = _media_mark(msg)
    if mark:
        text = f"{mark} {text}".strip()
    if not text:
        return None
    date = msg.date
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    return {
        "id": msg.id,
        "date": date.astimezone(timezone.utc).isoformat(),
        "from": "operator" if msg.out else "user",
        "text": text,
    }


def _is_client(entity, me_id: int) -> bool:
    return (
        entity is not None
        and not getattr(entity, "bot", False)
        and not getattr(entity, "deleted", False)
        and not getattr(entity, "is_self", False)
        and entity.id not in (me_id, _TELEGRAM_SERVICE_ID)
    )


def _person_name(entity) -> str:
    parts = [getattr(entity, "first_name", None), getattr(entity, "last_name", None)]
    return " ".join(p for p in parts if p) or ""


class HistoryExporter:
    """Одна выгрузка на сервис; прогресс и путь к файлу — в памяти процесса."""

    def __init__(self, fallback, exports_dir: Path):
        self.fallback = fallback
        self.dir = Path(exports_dir)
        self._jobs: dict[int, dict] = {}

    def status(self, service_id: int) -> dict:
        job = self._jobs.get(service_id)
        if not job:
            return {"state": "idle"}
        return {k: v for k, v in job.items() if k not in ("task", "path")}

    def file_for(self, service_id: int) -> Path | None:
        job = self._jobs.get(service_id)
        if job and job.get("state") == "done" and job.get("path") and job["path"].exists():
            return job["path"]
        return None

    async def start(self, service_id: int) -> dict:
        job = self._jobs.get(service_id)
        if job and job.get("state") == "running":
            raise RuntimeError("Выгрузка уже идёт")
        cfg = await self.fallback.settings(service_id)
        config = cfg.get("config") or {}
        if not config.get("session"):
            raise ValueError("Сначала подключите аккаунт поддержки (резервная отправка)")
        if job and job.get("path"):
            job["path"].unlink(missing_ok=True)
        job = {"state": "running", "chats_done": 0, "chats_total": 0,
               "messages": 0, "error": "", "started_at": time.time()}
        self._jobs[service_id] = job
        job["task"] = asyncio.create_task(self._run(service_id, config, job))
        return self.status(service_id)

    async def _run(self, service_id: int, config: dict, job: dict) -> None:
        # Отдельный клиент: кэшированный отправитель резервного канала в это
        # время может досылать ответы операторов, делить с ним сессию незачем.
        sender = TelethonSender(config)
        try:
            client = await sender._connect()
            chats = await self._collect(client, job)
            me = await client.get_me()
            account = ("@" + me.username) if getattr(me, "username", None) else str(me.id)
            self.dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            path = self.dir / f"history_{service_id}_{stamp}_{secrets.token_hex(4)}.json"
            payload = {
                "format": HISTORY_FORMAT,
                "account": account,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "chats": chats,
            }
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            job.update(state="done", path=path, filename=path.name,
                       finished_at=time.time())
        except ImportError as e:
            job.update(state="error", error=_install_hint(e))
        except Exception as e:
            job.update(state="error", error=redact(e)[:300])
            print(f"[history] выгрузка сервиса {service_id} упала: {redact(e)}")
        finally:
            await sender.close()

    async def _collect(self, client, job: dict) -> list[dict]:
        from telethon.errors import FloodWaitError

        me = await client.get_me()
        dialogs = [d for d in await client.get_dialogs()
                   if d.is_user and _is_client(d.entity, me.id)]
        job["chats_total"] = len(dialogs)

        chats = []
        for dialog in dialogs:
            entity = dialog.entity
            while True:
                try:
                    messages = []
                    async for msg in client.iter_messages(entity, reverse=True):
                        item = message_to_json(msg)
                        if item:
                            messages.append(item)
                    break
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds + 1)
            if messages:
                chats.append({
                    "chat_id": str(entity.id),
                    "name": _person_name(entity),
                    "username": getattr(entity, "username", None) or "",
                    "messages": messages,
                })
                job["messages"] += len(messages)
            job["chats_done"] += 1
        return chats

    async def close(self) -> None:
        for job in self._jobs.values():
            task = job.get("task")
            if task and not task.done():
                task.cancel()
