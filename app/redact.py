"""Вырезание из текста всего, по чему видно, куда ходит панель.

Панель обращается к Support API ВПН-а, к Remnawave, к вебхуку n8n и к Bot API
Telegram. Адреса этих апстримов, токены и куки — внутреннее устройство, и
наружу они попадать не должны ни одним из трёх путей: в ответе API, в тексте
ошибки на экране оператора и в логе процесса.

`redact` работает по образцу, а не по списку известных значений: текст
исключения приходит из aiohttp и содержит адрес в свободной форме
(«Cannot connect to host api.example.com:443 ssl:default»), а список секретов
неизбежно отстанет от того, что реально настроено.

`mask_*` — про другое: показать админу, что значение задано и какое оно
примерно, не называя хост.
"""

import re

HIDDEN = "[скрыто]"

# Порядок важен: сначала целые URL, иначе внутри них останутся куски host:port.
_URL_RE = re.compile(
    r"\b(?:https?|wss?|amqps?|redis|postgres(?:ql)?)://[^\s'\"<>\\)]+",
    re.IGNORECASE,
)
# «host api.example.com:443», «host='db' port=5432» — форма, в которой адрес
# приходит из aiohttp и asyncpg уже без схемы.
_HOST_KV_RE = re.compile(
    r"\b(host|hostname|server)\b\s*[=:]?\s*'?\"?"
    r"([A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+|\d{1,3}(?:\.\d{1,3}){3})"
    r"'?\"?(?::\d+)?",
    re.IGNORECASE,
)
# Голый домен или IP, оставшийся в тексте сам по себе.
_BARE_HOST_RE = re.compile(
    r"\b(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+"
    r"(?:[A-Za-z]{2,24})\b(?::\d{2,5})?"
)
_IP_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b(?::\d{2,5})?")
# Токен бота Telegram: 123456789:AA… — он же уезжает внутри URL файлов, где
# стоит сразу за «bot», без границы слова перед цифрами.
_BOT_TOKEN_RE = re.compile(r"(?:bot)?\d{6,}:[A-Za-z0-9_-]{30,}")
# Заголовок Cookie/Authorization целиком, вместе со значением.
# Значение забирается до конца строки или до разделителя списка заголовков:
# иначе «Authorization: Bearer eyJ…» спрятало бы только слово «Bearer».
_HEADER_SECRET_RE = re.compile(
    r"\b(cookie|set-cookie|authorization|x-api-key)\b\s*[=:]\s*[^,;'\"\n]+",
    re.IGNORECASE,
)

# Домены, которые ничего не выдают: они одинаковы у всех и стоят в текстах
# исключений стандартной библиотеки. Прятать их — только мусорить сообщение.
_KEEP = {"json.org", "python.org", "example.com"}

# «remnawave.py» и «config.yml» устроены ровно как домен: метка, точка,
# двухбуквенный «домен верхнего уровня». Без этого списка фильтр вырезал бы
# имена файлов из трейсбеков и читать логи стало бы нечем.
_FILE_EXT = {
    "py", "pyc", "pyi", "js", "jsx", "ts", "tsx", "json", "md", "txt", "rst",
    "html", "htm", "css", "scss", "sh", "bash", "yml", "yaml", "toml", "ini",
    "cfg", "conf", "env", "lock", "log", "sql", "csv", "tsv", "xml", "svg",
    "png", "jpg", "jpeg", "gif", "webp", "ico", "mp3", "mp4", "ogg", "oga",
    "wav", "webm", "pdf", "doc", "docx", "xls", "xlsx", "zip", "gz", "tar",
    "so", "dll", "exe", "bin", "dat", "tmp", "bak", "old", "sample",
}


# Строки uvicorn про саму панель: лог доступа и адрес, на котором она
# поднялась. Прятать в них нечего — там входящий клиент и свой порт, — а вот
# без них не понять ни откуда пришёл запрос, ни куда стучаться самому.
# Различаем по форме строки, а не по значению адреса: апстрим вполне может
# жить на приватном IP («Cannot connect to host 10.8.0.5:8080»), и он
# прятаться обязан.
_OWN_LOG_RE = (
    re.compile(r'^INFO:\s+\S+:\d+ - "'),          # 127.0.0.1:54321 - "POST /api/…"
    re.compile(r"^INFO:\s+Uvicorn running on "),  # адрес и порт самой панели
)


def _keep(host: str) -> bool:
    host = host.split(":")[0].lower()
    return host in _KEEP or host.rsplit(".", 1)[-1] in _FILE_EXT


def redact(text) -> str:
    """Текст без адресов, токенов и кук.

    Принимает что угодно (в логи летят и исключения, и объекты) — приводит к
    строке сама. Разбор построчный: в `sys.stdout.write` прилетают целые куски
    вывода, а «свои» строки uvicorn надо пропускать поштучно.
    """
    if text is None:
        return ""
    out = text if isinstance(text, str) else str(text)
    if not out:
        return out
    if "\n" in out:
        return "\n".join(_redact_line(line) for line in out.split("\n"))
    return _redact_line(out)


def _redact_line(out: str) -> str:
    if any(p.search(out) for p in _OWN_LOG_RE):
        return out
    out = _HEADER_SECRET_RE.sub(lambda m: f"{m.group(1)}={HIDDEN}", out)
    out = _BOT_TOKEN_RE.sub(HIDDEN, out)
    out = _URL_RE.sub(HIDDEN, out)
    out = _HOST_KV_RE.sub(lambda m: f"{m.group(1)}={HIDDEN}", out)
    out = _IP_RE.sub(HIDDEN, out)
    out = _BARE_HOST_RE.sub(lambda m: m.group(0) if _keep(m.group(0)) else HIDDEN, out)
    return out


def mask_url(url: str) -> str:
    """Адрес для показа админу: схема и путь остаются, хост — нет.

    `https://api.example.com/nemo/api/v1` → `https://…/nemo/api/v1`. По такой
    маске видно, что адрес задан и куда именно в API он смотрит, но не видно,
    на какой машине это API живёт.
    """
    url = (url or "").strip()
    if not url:
        return ""
    m = re.match(r"^([a-zA-Z][\w+.-]*://)?[^/]*(/.*)?$", url)
    if not m:
        return "…"
    scheme, path = m.group(1) or "", m.group(2) or ""
    return f"{scheme}…{path}"


def mask_tail(value: str, keep: int = 4) -> str:
    """Хвост идентификатора — чтобы отличить один сохранённый от другого.

    `AAHhGgFf1122` → `…1122`. Короткое значение прячется целиком: у него хвост
    и есть всё значение.
    """
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "…"
    return "…" + value[-keep:]
