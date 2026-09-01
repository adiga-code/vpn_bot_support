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


def _num_prefix(header: str) -> tuple[str, str]:
    """(текст заголовка без номера, номер как дефисный слаг-префикс).
    "02.1 Как определить" → ("Как определить", "02-1-"); без номера — ("", "")."""
    m = re.match(r"^(\d+(?:\.\d+)*)[.)]?\s*", header)
    if not m:
        return header, ""
    return header[m.end():].strip(), m.group(1).replace(".", "-") + "-"


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

    def add(title: str, body: str, keywords: list[str], id_prefix: str):
        body = re.sub(r"\n-{3,}\s*$", "", (body or "").strip())
        if len(body) < 20:
            return
        pieces = _split_by_paragraphs(body)
        for i, piece in enumerate(pieces):
            part_title = title if i == 0 else f"{title} — часть {i + 1}"
            slug = _make_slug(part_title, seen, prefix=id_prefix)
            chunks.append({
                "id":       slug,
                "title":    part_title,
                "category": _guess_category(title, keywords),
                "keywords": keywords,
                "content":  f"{part_title}\n\n{piece}",
            })

    for part in parts[1:]:
        header, _, section_body = part.partition("\n")
        parent_title, parent_prefix = _num_prefix(header.strip())
        parent_kw = _extract_keywords(section_body)

        sub_parts = re.split(r"(?m)^###\s+", section_body)
        subs = sub_parts[1:]
        if not subs:
            # Подпунктов нет — тема остаётся одним чанком целиком.
            add(parent_title, section_body, parent_kw, parent_prefix)
            continue
        # Текст до первого "### " (определения, строка «Запросы:») — свой
        # чанк, без самой строки «Запросы:».
        intro = re.sub(r"(?mi)^\s*[*_]*Запросы:.*$", "", sub_parts[0]).strip()
        if len(intro) >= 20:
            add(parent_title, intro, parent_kw, parent_prefix)
        for sp in subs:
            sub_header, _, sub_body = sp.partition("\n")
            sub_title, sub_prefix = _num_prefix(sub_header.strip())
            title = f"{parent_title} — {sub_title}".strip(" —") if sub_title else parent_title
            # Номер у "### " уже включает номер родителя ("02.1"), поэтому
            # свой префикс достаточен и без родительского — конфликтов между
            # темами он не даёт.
            add(title, sub_body, parent_kw + _extract_keywords(sub_body),
                sub_prefix or parent_prefix)
    return chunks or None


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
) -> list[dict]:
    """Full pipeline: text → chunks → embeddings (OpenAI) → Qdrant.

    Structured markdown ("## " sections) is split deterministically; the
    chat LLM is only a fallback for unstructured documents.
    """
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
        await ensure_collection(qdrant_url, collection)
        await upsert_to_qdrant(chunks, qdrant_url, collection)
        print(f"[KB] Upserted {len(chunks)} vectors to Qdrant collection '{collection}'")
        for c in chunks:
            c.pop("embedding", None)
        return chunks
    except Exception as e:
        print(f"[KB] Exception in process_document: {e}")
        raise
