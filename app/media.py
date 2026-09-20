"""Приём чужих файлов на свой домен.

Аватар клиента и присланное им видео раньше доезжали до панели ссылкой на
api.telegram.org — а в такой ссылке стоит токен бота. Браузер оператора шёл по
ней сам, и токен оказывался и в DevTools, и в истории, и на любом прокси по
пути.

Поэтому вход один: что бы ни прислал воркфлоу, панель кладёт файл в своё
хранилище и запоминает только свою ссылку. Тогда исправность воркфлоу
перестаёт быть условием — чужой адрес просто не может попасть в базу.
"""

import re
import uuid
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

from app.redact import redact

# 20 МБ: Telegram и так не отдаёт файлы больше 20 МБ по Bot API, а неизвестный
# источник не должен уметь занять диск панели.
MAX_BYTES = 20 * 1024 * 1024
TIMEOUT_SECONDS = 20


# «host.tld/что-то» или «host.tld» — адрес чужого сервера, у которого потеряли
# схему. Telegram-овский file_id под это не подходит: в нём нет ни точки в
# начале, ни слеша, — поэтому по нему за файлом никто не пойдёт.
_HOSTLIKE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+(:\d+)?(/|$)", re.I)


def looks_like_url(value) -> bool:
    """Значение — ссылка, а не Telegram-овский file_id?

    Схема может отсутствовать: n8n кладёт в file_id то, что вернула панель, а
    панель до этой правки отдавала адрес без «https://».
    """
    v = str(value or "").strip()
    if not v:
        return False
    if v.startswith(("http://", "https://", "//")):
        return True
    return bool(_HOSTLIKE.match(v))


def absolutize(url: str, base: str = "") -> str:
    """Схема к ссылке, которая её потеряла.

    Без схемы «panel.example.com/api/files/x.jpg» — относительный путь: браузер
    оператора просит его у текущей страницы и получает 404, а n8n не скачает
    вложение вовсе. Путь от корня остаётся относительным, когда base пуст, —
    так панель работает и без BASE_URL.
    """
    u = (url or "").strip()
    if not u or "://" in u:
        return u
    if u.startswith("//"):
        return f"https:{u}"
    if u.startswith("/"):
        return f"{base.rstrip('/')}{u}" if base else u
    if _HOSTLIKE.match(u):
        return f"https://{u}"
    return u


def is_internal(url: str, own_prefixes: list[str]) -> bool:
    """Ссылка уже наша? Относительный путь — всегда наш.

    Адрес без схемы разбирается как абсолютный, если похож на host/path: иначе
    «api.telegram.org/file/bot<токен>/…» сошёл бы за свой путь и токен бота
    осел бы в базе.
    """
    url = (url or "").strip()
    if not url:
        return False
    if not looks_like_url(url):
        return True
    absolute = absolutize(url)
    return any(p and absolute.startswith(p) for p in own_prefixes)


def own_prefixes(settings) -> list[str]:
    return settings.public_file_prefixes()


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

    Наша ссылка возвращается как есть, разве что с дописанной схемой:
    относительный адрес не откроет ни браузер оператора, ни n8n. Недоступный
    источник — пустая строка:
    сообщение оператору важнее вложения, а падать из-за чужого сервера панель
    не должна. Адрес в лог не попадает даже при ошибке.
    """
    url = (url or "").strip()
    if not url:
        return url
    if is_internal(url, own_prefixes(settings)):
        # Своя ссылка, но, возможно, без схемы — отдаём её пригодной к открытию.
        return absolutize(url, settings.public_base_url())
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
