"""Приём чужих файлов на свой домен.

Аватар клиента и присланное им видео раньше доезжали до панели ссылкой на
api.telegram.org — а в такой ссылке стоит токен бота. Браузер оператора шёл по
ней сам, и токен оказывался и в DevTools, и в истории, и на любом прокси по
пути.

Поэтому вход один: что бы ни прислал воркфлоу, панель кладёт файл в своё
хранилище и запоминает только свою ссылку. Тогда исправность воркфлоу
перестаёт быть условием — чужой адрес просто не может попасть в базу.
"""

import uuid
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

from app.redact import redact

# 20 МБ: Telegram и так не отдаёт файлы больше 20 МБ по Bot API, а неизвестный
# источник не должен уметь занять диск панели.
MAX_BYTES = 20 * 1024 * 1024
TIMEOUT_SECONDS = 20


def is_internal(url: str, own_prefixes: list[str]) -> bool:
    """Ссылка уже наша? Относительный путь — всегда наш."""
    url = (url or "").strip()
    if not url:
        return False
    if not urlparse(url).netloc:
        return True
    return any(p and url.startswith(p) for p in own_prefixes)


def own_prefixes(settings) -> list[str]:
    return [(settings.BASE_URL or "").rstrip("/"),
            (settings.S3_PUBLIC_URL or "").rstrip("/")]


def _suffix(url: str, content_type: str = "") -> str:
    ext = Path(urlparse(url).path).suffix
    if ext and len(ext) <= 6:
        return ext
    return {
        "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
        "video/mp4": ".mp4", "audio/ogg": ".oga", "audio/mpeg": ".mp3",
    }.get((content_type or "").split(";")[0].strip(), "")


async def internalize(url: str, storage, settings) -> str:
    """Чужой файл → ссылка на своё хранилище.

    Наша ссылка возвращается как есть. Недоступный источник — пустая строка:
    сообщение оператору важнее вложения, а падать из-за чужого сервера панель
    не должна. Адрес в лог не попадает даже при ошибке.
    """
    url = (url or "").strip()
    if not url or is_internal(url, own_prefixes(settings)):
        return url
    try:
        timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    print(f"[media] источник ответил HTTP {resp.status} — вложение пропущено")
                    return ""
                content = await resp.content.read(MAX_BYTES + 1)
                if len(content) > MAX_BYTES:
                    print(f"[media] вложение больше {MAX_BYTES // 1024 // 1024} МБ — пропущено")
                    return ""
                ctype = resp.headers.get("Content-Type", "")
        return await storage.save(content, f"{uuid.uuid4().hex}{_suffix(url, ctype)}")
    except Exception as e:
        print(f"[media] не удалось забрать вложение: {redact(e)}")
        return ""
