from __future__ import annotations

import json
import re
import uuid
from typing import TYPE_CHECKING

from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

if TYPE_CHECKING:
    from app.ai_client import ChatClient

_EMBED_MODEL = "text-embedding-3-small"
_EMBED_DIMS  = 1536
_BATCH_SIZE  = 400

_CHUNKING_PROMPT = """You are a knowledge base indexing assistant. Your task is to parse the provided support documentation and split it into semantically meaningful, self-contained chunks suitable for vector search.

## RULES FOR CHUNKING

Each chunk must:
- Cover ONE specific topic or scenario (e.g., one device setup, one FAQ item, one troubleshooting branch)
- Be self-contained — readable and useful WITHOUT context from other chunks
- Include relevant keywords a user might actually type (in Russian and English)
- Be 100–400 words maximum

## OUTPUT FORMAT

Return a JSON object with a single "chunks" key holding an array:

{
  "chunks": [
    {
      "id": "unique_slug",
      "category": "troubleshooting | setup | payment | faq | escalation",
      "title": "Short descriptive title",
      "keywords": ["keyword1", "keyword2", ...],
      "content": "Full self-contained text of this chunk"
    }
  ]
}

## CHUNKING STRATEGY

Split the document into chunks following this logic:

1. Each device setup → separate chunk (Windows, macOS, iOS, Android TV, Steam Deck, Oculus)
2. Each troubleshooting scenario → separate chunk
3. Each payment/billing topic → separate chunk
4. Each FAQ row → can be grouped by theme (2–4 related rows per chunk)
5. Escalation cases → one chunk

## IMPORTANT

- Preserve original Russian phrases exactly as written (e.g., "Подключить устройство", "Личный кабинет") — users will search with these exact words
- Do NOT summarize or rephrase instructions — keep them complete and actionable
- Do NOT merge unrelated topics into one chunk
- Return ONLY valid JSON. No markdown, no explanation, no preamble."""


_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _translit(text: str) -> str:
    return "".join(_TRANSLIT.get(ch, ch) for ch in text.lower())


def _make_slug(title: str, existing: set[str], prefix: str = "") -> str:
    """`prefix` (обычно номер раздела, уже переведённый в дефисы: "02-1-") идёт
    ПЕРЕД обрезкой транслита на 60 символов, а не после — иначе у длинных
    заголовков с общим началом ("Ограничения мобильного интернета: обычная
    проблема или белые списки — ...") транслит обрезается в одну и ту же
    строку, номер раздела теряется, и слаги схлопываются в один: последний
    чанк с таким id в цикле загрузки молча перезаписывает все предыдущие
    (и в kb_articles, и в Qdrant — оба ключа по id детерминированы)."""
    base = (prefix + re.sub(r"[^a-z0-9]+", "-", _translit(title).strip()))[:60].strip("-") or "chunk"
    slug = base
    i = 2
    while slug in existing:
        slug = f"{base}-{i}"
        i += 1
    existing.add(slug)
    return slug


make_slug = _make_slug  # для ручного добавления статей в web_server


def _split_by_paragraphs(body: str, max_words: int = 350) -> list[str]:
    """Разбить длинный текст по границам абзацев, а не потоком слов — иначе
    готовая пошаговая инструкция («Открыв меню бота… Нажмите…») рвётся
    посередине шага. Абзац длиннее предела сам по себе не режется: это
    страховка от одного гигантского ### на другом документе, а не жёсткая
    гарантия верхней границы — рвать инструкцию хуже, чем изредка превысить
    лимит на один цельный абзац."""
    paragraphs = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    if not paragraphs:
        return [body] if body.strip() else []
    parts: list[str] = []
    current: list[str] = []
    count = 0
    for p in paragraphs:
        words = len(p.split())
        if current and count + words > max_words:
            parts.append("\n\n".join(current))
            current, count = [p], words
        else:
            current.append(p)
            count += words
    if current:
        parts.append("\n\n".join(current))
    return parts or [body]


def _guess_category(title: str, keywords: list[str]) -> str:
    text = (title + " " + " ".join(keywords)).lower()
    if any(w in text for w in ("оператор", "ручная проверка", "handoff")):
        return "escalation"
    if any(w in text for w in ("не работает", "не подключ", "не открыва", "не грузит",
                               "ошибк", "timeout", "диагностик", "отключа", "сломал")):
        return "troubleshooting"
    if any(w in text for w in ("подключить", "подключение", "установить", "скачать",
                               "роутер", "телевизор", "приставк", "устройство", "клиент")):
        return "setup"
    if any(w in text for w in ("оплат", "покупк", "продлен", "возврат",
                               "промокод", "тариф", "списание")):
        return "payment"
    return "faq"


def _extract_keywords(block: str) -> list[str]:
    """Достаёт строку «Запросы: a; b; c», терпимо к markdown-обрамлению вокруг
    метки (например «**Запросы:**»)."""
    m = re.search(r"(?mi)^\s*[*_]*Запросы:[*_]*\s*(.+?)\s*$", block)
    if not m:
        return []
    return [k.strip(" .*_") for k in m.group(1).split(";") if k.strip(" .*_")]


CATEGORY_LABELS = {
    "troubleshooting": "Решение проблем",
    "setup":           "Настройка",
    "payment":         "Оплата",
    "faq":             "FAQ",
    "escalation":      "Эскалация",
}
_CATEGORY_RE = re.compile(r"(?mi)^[ \t]*[*_]*Категория:[*_]*[ \t]*(.+?)[ \t]*$")


def _extract_category(block: str) -> str | None:
    """Необязательная строка «Категория: Настройка» (или код: «setup»).
    Без неё категория угадывается по заголовку и запросам. Выгрузка базы
    пишет её в каждую статью — иначе категория, выставленная вручную,
    при повторной загрузке угадывалась бы заново."""
    m = _CATEGORY_RE.search(block or "")
    if not m:
        return None
    value = m.group(1).strip(" .*_").lower()
    for code, label in CATEGORY_LABELS.items():
        if value in (code, label.lower()):
            return code
    return None


_NUM_RE = re.compile(r"^(\d+(?:\.\d+)*)[.)]?\s*")


def split_number(header: str) -> tuple[str, str]:
    """(номер раздела, текст заголовка без номера).
    "02.1 Как определить" → ("02.1", "Как определить"); без номера — ("", header)."""
    m = _NUM_RE.match(header)
    if not m:
        return "", header
    return m.group(1), header[m.end():].strip()


def number_key(title: str) -> tuple[int, ...] | None:
    """Ключ сортировки по ведущему номеру заголовка: "02.10 …" → (2, 10).
    Сравнение числовое, поэтому 02.10 идёт после 02.9, а не перед ним."""
    num, _ = split_number(title or "")
    return tuple(int(p) for p in num.split(".")) if num else None


def _num_prefix(header: str) -> tuple[str, str, str]:
    """(текст заголовка без номера, номер как дефисный слаг-префикс, номер).
    "02.1 Как определить" → ("Как определить", "02-1-", "02.1"); без номера —
    (header, "", "")."""
    num, rest = split_number(header)
    if not num:
        return header, "", ""
    return rest, num.replace(".", "-") + "-", num


def compose_content(title: str, body: str) -> str:
    """Текст чанка = заголовок + пустая строка + тело: заголовок попадает и в
    эмбеддинг, и в выдачу ИИ. Тот же формат у загрузки и у ручной правки."""
    return f"{title}\n\n{body.strip()}"


def split_content(title: str, content: str) -> str:
    """Тело статьи без ведущей строки-заголовка — для формы редактирования.
    У статей, загруженных до того, как номер стал оставаться в заголовке,
    первая строка — заголовок без номера; её тоже отрезаем."""
    head, sep, rest = (content or "").partition("\n")
    head = head.strip()
    if sep and head and head in (title.strip(), split_number(title.strip())[1]):
        return rest.lstrip("\n")
    return content or ""


def parse_markdown_sections(text: str) -> list[dict] | None:
    """Deterministically split a structured markdown document into KB chunks.

    Каждая тема "## " делится дальше по своим "### " сценариям — так один
    чанк покрывает узкий сценарий, а не всю раздутую тему целиком, и векторный
    поиск попадает точнее. Каждый чанк несёт заголовок родительской "## "-темы
    как контекст и наследует её строку «Запросы:» (метка может быть жирной).
    "## "-раздел без "### "-подпунктов остаётся одним чанком (как раньше).
    Чанк длиннее ~350 слов режется дальше по границам абзацев — см.
    `_split_by_paragraphs`. Возвращает None, если в документе меньше двух
    "## "-разделов — тогда вызывающий код падает на чанкинг через LLM.
    """
    parts = re.split(r"(?m)^##\s+", text)
    if len(parts) < 3:  # parts[0] — преамбула до первого заголовка
        return None
    seen: set[str] = set()
    chunks: list[dict] = []

    def add(title: str, body: str, keywords: list[str], id_prefix: str, num: str,
            category: str | None = None):
        body = _CATEGORY_RE.sub("", body or "")
        body = re.sub(r"\n-{3,}\s*$", "", body.strip())
        if len(body) < 20:
            return
        pieces = _split_by_paragraphs(body)
        for i, piece in enumerate(pieces):
            part_title = title if i == 0 else f"{title} — часть {i + 1}"
            # Слаг — из заголовка БЕЗ номера (номер уже в id_prefix): id статей
            # и точек Qdrant не меняются оттого, что номер теперь остаётся
            # в видимом заголовке.
            slug = _make_slug(part_title, seen, prefix=id_prefix)
            shown = f"{num} {part_title}" if num else part_title
            chunks.append({
                "id":       slug,
                "title":    shown,
                "category": category or _guess_category(title, keywords),
                "keywords": keywords,
                "content":  compose_content(shown, piece),
                "position": len(chunks),
            })

    for part in parts[1:]:
        header, _, section_body = part.partition("\n")
        parent_title, parent_prefix, parent_num = _num_prefix(header.strip())
        parent_kw = _extract_keywords(section_body)

        sub_parts = re.split(r"(?m)^###\s+", section_body)
        subs = sub_parts[1:]
        if not subs:
            # Подпунктов нет — тема остаётся одним чанком целиком.
            add(parent_title, section_body, parent_kw, parent_prefix, parent_num,
                _extract_category(section_body))
            continue
        # Категория темы берётся только из текста до первого "### " — иначе
        # строка «Категория:» подпункта приписалась бы всей теме.
        parent_cat = _extract_category(sub_parts[0])
        # Текст до первого "### " (определения, строка «Запросы:») — свой
        # чанк, без самой строки «Запросы:».
        intro = re.sub(r"(?mi)^\s*[*_]*Запросы:.*$", "", sub_parts[0]).strip()
        if len(intro) >= 20:
            add(parent_title, intro, parent_kw, parent_prefix, parent_num, parent_cat)
        for sp in subs:
            sub_header, _, sub_body = sp.partition("\n")
            sub_title, sub_prefix, sub_num = _num_prefix(sub_header.strip())
            title = f"{parent_title} — {sub_title}".strip(" —") if sub_title else parent_title
            # Номер у "### " уже включает номер родителя ("02.1"), поэтому
            # свой префикс достаточен и без родительского — конфликтов между
            # темами он не даёт.
            add(title, sub_body, parent_kw + _extract_keywords(sub_body),
                sub_prefix or parent_prefix, sub_num or parent_num,
                _extract_category(sub_body) or parent_cat)
    return chunks or None


def export_markdown(articles: list[dict], heading: str) -> str:
    """База знаний обратно в markdown — в том формате, который принимает
    загрузка. Каждая статья — отдельный "## "-раздел с её заголовком (номер
    в начале), строками «Категория:» и «Запросы:» и текстом. При повторной
    загрузке такой файл даёт те же статьи: тот же заголовок, id, категорию и
    запросы — поэтому базу можно скачать, поправить в редакторе и загрузить
    обратно, не теряя ручных правок из панели.

    Разделы плоские, без "### ": статья, добавленная в панели, не обязана
    называться «Тема — Сценарий», и вложение исказило бы её заголовок.
    Строки «Запросы:»/«Категория:», которые уже есть в тексте статьи,
    заменяются одной актуальной — список запросов в панели мог измениться."""
    label_re = re.compile(r"(?mi)^[ \t]*[*_]*(?:Запросы|Категория):.*(?:\n|$)")
    lines = [f"# {heading}", ""]
    for a in articles:
        body = label_re.sub("", split_content(a["title"], a["content"])).strip()
        lines += [f"## {a['title']}", ""]
        lines.append(f"**Категория:** {CATEGORY_LABELS.get(a['category'], a['category'])}")
        keywords = a.get("keywords") or []
        if keywords:
            lines.append(f"**Запросы:** {'; '.join(keywords)}")
        lines += ["", body, ""]
    return "\n".join(lines)


async def chunk_document(text: str, chat_client: "ChatClient") -> list[dict]:
    """Call the configured chat LLM to split the document into KB chunks."""
    # Removed input length limit to allow full text processing
    attempt = 0
    max_attempts = 3
    while attempt < max_attempts:
        try:
            # gpt-5-mini is a reasoning model: it rejects any temperature
            # other than the default, so the parameter is omitted entirely.
            response = await chat_client.client.chat.completions.create(
                model=chat_client.model,
                messages=[
                    {"role": "system", "content": _CHUNKING_PROMPT},
                    {"role": "user",   "content": text},
                ],
                response_format={"type": "json_object"},
            )
            choice = response.choices[0]
            raw = choice.message.content
            print(f"[chunk_document] Raw response: {len(raw or '')} chars, finish_reason={choice.finish_reason}")
            if choice.finish_reason == "length":
                # Output hit the model's token limit — the JSON is truncated
                # and unrecoverable; retrying the same request won't help.
                print("[chunk_document] Response truncated by output token limit; the document is too large for a single request.")
                return []
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                chunks = parsed
            elif isinstance(parsed, dict):
                # If dict has 'chunks' key with list, use it; else wrap dict in list
                if "chunks" in parsed and isinstance(parsed["chunks"], list):
                    chunks = parsed["chunks"]
                else:
                    chunks = [parsed]
            else:
                chunks = []
            print(f"[chunk_document] Number of chunks received: {len(chunks)}")
            break
        except Exception as e:
            print(f"[chunk_document] Error during chunking attempt {attempt+1}: {e}")
            attempt += 1
            if attempt == max_attempts:
                print("[chunk_document] Max attempts reached, returning empty list.")
                return []
            # Optionally, modify input_text or prompt here for retry
    seen: set[str] = set()
    result = []
    for c in chunks:
        # Defensive check: if c is a string, wrap it in a dict with id and content
        if isinstance(c, str):
            c = {"id": c, "title": c, "category": "faq", "keywords": [], "content": c}
        # Filter out chunks that are too short or empty
        content = c.get("content", "")
        if not content or len(content.strip()) < 20:
            continue
        slug = _make_slug(c.get("id") or c.get("title", "chunk"), seen)
        result.append({
            "id":       slug,
            "title":    c.get("title", ""),
            "category": c.get("category", "faq"),
            "keywords": c.get("keywords", []),
            "content":  content,
            "position": len(result),
        })
    print(f"[chunk_document] Number of chunks after filtering: {len(result)}")
    return result


def _embed_text(chunk: dict) -> str:
    """Text sent to the embedding model: title and keywords are included so
    user queries match the exact phrases from the «Запросы:» lines."""
    parts = [chunk.get("title", ""), "; ".join(chunk.get("keywords", [])), chunk["content"]]
    return "\n".join(p for p in parts if p)


async def embed_chunks(chunks: list[dict], openai_key: str) -> list[dict]:
    """Embed chunks using OpenAI text-embedding-3-small (always OpenAI)."""
    client = AsyncOpenAI(api_key=openai_key)
    texts = [_embed_text(c) for c in chunks]
    embeddings = []
    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i: i + _BATCH_SIZE]
        resp = await client.embeddings.create(model=_EMBED_MODEL, input=batch)
        embeddings.extend([item.embedding for item in resp.data])
    for chunk, emb in zip(chunks, embeddings):
        chunk["embedding"] = emb
    return chunks


async def ensure_collection(qdrant_url: str, collection: str):
    """Create Qdrant collection and payload index if they don't exist.

    У каждого ВПН-сервиса своя коллекция (services.qdrant_collection) — так
    базы знаний не смешиваются, а в n8n имя коллекции остаётся обычным
    параметром ноды.
    """
    from qdrant_client.models import PayloadSchemaType
    client = AsyncQdrantClient(url=qdrant_url)
    try:
        await client.get_collection(collection)
    except Exception:
        await client.create_collection(
            collection,
            vectors_config=VectorParams(size=_EMBED_DIMS, distance=Distance.COSINE),
        )
    try:
        await client.create_payload_index(
            collection,
            field_name="metadata.article_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )
    except Exception:
        pass
    await client.close()


async def read_from_qdrant(qdrant_url: str, collection: str) -> list[dict]:
    """Все статьи коллекции в формате чанков БД (без векторов). Нужна, чтобы
    вернуть в панель статьи, которые в Qdrant есть, а в таблице kb_articles
    пропали. Коллекции нет — пустой список. Ошибка связи пробрасывается:
    «Qdrant недоступен» и «в коллекции пусто» — разные вещи."""
    client = AsyncQdrantClient(url=qdrant_url)
    try:
        try:
            await client.get_collection(collection)
        except Exception:
            if await _collection_missing(client, collection):
                return []
            raise
        chunks, offset = [], None
        while True:
            points, offset = await client.scroll(
                collection_name=collection, limit=256, offset=offset,
                with_payload=True, with_vectors=False,
            )
            for p in points:
                payload = p.payload or {}
                meta = payload.get("metadata") or {}
                article_id, content = meta.get("article_id"), payload.get("content")
                if not article_id or not content:
                    continue
                chunks.append({
                    "id":       article_id,
                    "title":    meta.get("title") or article_id,
                    "category": meta.get("category") or "faq",
                    "keywords": meta.get("keywords") or [],
                    "content":  content,
                })
            if offset is None:
                break
    finally:
        await client.close()
    # Порядок документа: по номеру в начале заголовка, статьи без номера — в
    # конце в порядке Qdrant. get_kb_articles всё равно сортирует по номеру,
    # position нужен только как запасной порядок.
    chunks.sort(key=lambda c: (0, number_key(c["title"])) if number_key(c["title"]) is not None
                else (1, ()))
    for i, c in enumerate(chunks):
        c["position"] = i
    return chunks


async def restore_service_kb(db, service: dict, qdrant_url: str) -> int:
    """Вернуть в панель статьи сервиса, которые есть в его коллекции Qdrant, а
    в таблице пропали. Ничего не удаляет и не перезаписывает. Возвращает число
    восстановленных статей."""
    chunks = await read_from_qdrant(qdrant_url, service["qdrant_collection"])
    return await db.restore_kb_articles(service["id"], chunks) if chunks else 0


async def restore_all_kb_once(db, qdrant_url: str):
    """Разовое восстановление после смены первичного ключа kb_articles:
    у сервисов, чьи статьи были «перевешены» чужой загрузкой, список в панели
    пуст при полном Qdrant. Флаг ставится только если Qdrant ответил по всем
    сервисам — иначе попытка повторится при следующем старте. Запускается
    после старта, чтобы недоступный Qdrant не задерживал панель."""
    if await db.get_setting("kb_restore_v1"):
        return
    ok = True
    for service in await db.get_services(only_active=False):
        try:
            restored = await restore_service_kb(db, service, qdrant_url)
            if restored:
                print(f"[kb] восстановлено из Qdrant: {restored} статей "
                      f"сервиса '{service['slug']}'")
        except Exception as e:
            ok = False
            print(f"[kb] восстановление '{service['slug']}' не удалось: {e}")
    if ok:
        await db.set_setting("kb_restore_v1", "1")


async def _collection_missing(client, collection: str) -> bool:
    try:
        names = {c.name for c in (await client.get_collections()).collections}
    except Exception:
        return False
    return collection not in names


async def delete_collection(qdrant_url: str, collection: str):
    """Полный сброс базы знаний одного сервиса."""
    client = AsyncQdrantClient(url=qdrant_url)
    try:
        await client.delete_collection(collection)
    except Exception:
        pass
    finally:
        await client.close()


def _point_id(article_id: str) -> str:
    # Deterministic: re-uploading the same document overwrites its points
    # instead of accumulating duplicates.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"kb:{article_id}"))


async def upsert_to_qdrant(chunks: list[dict], qdrant_url: str, collection: str):
    """Upsert embedded chunks into Qdrant."""
    client = AsyncQdrantClient(url=qdrant_url)
    points = [
        PointStruct(
            id=_point_id(c["id"]),
            vector=c["embedding"],
            payload={
                # "content"/"metadata" are the payload keys the n8n Qdrant
                # Vector Store node reads by default.
                "content": c["content"],
                "metadata": {
                    "article_id": c["id"],
                    "title":      c["title"],
                    "category":   c["category"],
                    "keywords":   c["keywords"],
                },
            },
        )
        for c in chunks
    ]
    await client.upsert(collection_name=collection, points=points)
    await client.close()


async def index_article(chunk: dict, openai_key: str, qdrant_url: str, collection: str):
    """Проиндексировать одну статью, добавленную или исправленную вручную.
    Point-id детерминирован по id статьи, поэтому правка перезаписывает
    прежнюю точку в Qdrant, а не плодит дубль."""
    item = dict(chunk)
    await embed_chunks([item], openai_key)
    await ensure_collection(qdrant_url, collection)
    await upsert_to_qdrant([item], qdrant_url, collection)


async def delete_from_qdrant(article_id: str, qdrant_url: str, collection: str):
    """Delete a point by article_id payload filter."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    client = AsyncQdrantClient(url=qdrant_url)
    try:
        await client.delete(
            collection_name=collection,
            points_selector=Filter(
                must=[FieldCondition(key="metadata.article_id", match=MatchValue(value=article_id))]
            ),
        )
    except Exception:
        pass
    await client.close()


async def process_document(
    text: str, chat_client: "ChatClient", openai_key: str, qdrant_url: str, collection: str,
    db=None, service_id: int = None,
) -> list[dict]:
    """Full pipeline: text → chunks → embeddings (OpenAI) → Qdrant.

    Structured markdown ("## " sections) is split deterministically; the
    chat LLM is only a fallback for unstructured documents.

    `db`/`service_id` — если заданы, загрузка ПОЛНОСТЬЮ заменяет прежнюю базу
    знаний этого сервиса, а не дополняет её: старая версия документа стирается
    после того, как новая успешно собрана и провекторизована (если чанкинг или
    эмбеддинги упали, рабочая база остаётся нетронутой). Без переустановки
    раздел, удалённый из документа при правке, навсегда оставался бы в поиске
    ИИ — с мелкими чанками по "### " это особенно заметно."""
    try:
        chunks = parse_markdown_sections(text)
        if chunks:
            print(f"[KB] Parsed {len(chunks)} markdown sections deterministically")
        else:
            print(f"[KB] No markdown structure found, chunking ({len(text)} chars) via {chat_client.model}...")
            chunks = await chunk_document(text, chat_client)
        if not chunks:
            print("[KB] No chunks created, skipping embedding and upsert.")
            return []
        print(f"[KB] Created {len(chunks)} chunks, embedding...")
        chunks = await embed_chunks(chunks, openai_key)
        if db is not None and service_id is not None:
            await db.reset_kb(service_id)
            await delete_collection(qdrant_url, collection)
        await ensure_collection(qdrant_url, collection)
        await upsert_to_qdrant(chunks, qdrant_url, collection)
        print(f"[KB] Upserted {len(chunks)} vectors to Qdrant collection '{collection}'")
        for c in chunks:
            c.pop("embedding", None)
        return chunks
    except Exception as e:
        print(f"[KB] Exception in process_document: {e}")
        raise
