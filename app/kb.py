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

_COLLECTION = "kb"
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


def _make_slug(title: str, existing: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", _translit(title).strip())[:60].strip("-") or "chunk"
    slug = base
    i = 2
    while slug in existing:
        slug = f"{base}-{i}"
        i += 1
    existing.add(slug)
    return slug


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


def parse_markdown_sections(text: str) -> list[dict] | None:
    """Deterministically split a structured markdown document into KB chunks.

    Expects sections delimited by "## " headers, optionally with a
    "Запросы: ..." line of user search phrases that becomes the keywords.
    Returns None when the document has fewer than two sections, so the
    caller can fall back to LLM chunking for unstructured documents.
    """
    parts = re.split(r"(?m)^##\s+", text)
    if len(parts) < 3:  # parts[0] is the preamble before the first header
        return None
    seen: set[str] = set()
    chunks = []
    for part in parts[1:]:
        header, _, body = part.partition("\n")
        header = header.strip()
        num_match = re.match(r"^(\d+)[.)]?\s*", header)
        title = header[num_match.end():].strip() if num_match else header
        body = re.sub(r"\n-{3,}\s*$", "", body.strip())
        if len(body) < 20:
            continue
        keywords = []
        kw_match = re.search(r"(?m)^Запросы:\s*(.+)$", body)
        if kw_match:
            keywords = [k.strip(" .") for k in kw_match.group(1).split(";") if k.strip(" .")]
        prefix = f"{num_match.group(1)}-" if num_match else ""
        slug = _make_slug(prefix + title, seen)
        chunks.append({
            "id":       slug,
            "title":    title,
            "category": _guess_category(title, keywords),
            "keywords": keywords,
            "content":  f"{title}\n\n{body}",
        })
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


async def ensure_collection(qdrant_url: str):
    """Create Qdrant collection and payload index if they don't exist."""
    from qdrant_client.models import PayloadSchemaType
    client = AsyncQdrantClient(url=qdrant_url)
    try:
        await client.get_collection(_COLLECTION)
    except Exception:
        await client.create_collection(
            _COLLECTION,
            vectors_config=VectorParams(size=_EMBED_DIMS, distance=Distance.COSINE),
        )
    try:
        await client.create_payload_index(
            _COLLECTION,
            field_name="metadata.article_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )
    except Exception:
        pass
    await client.close()


def _point_id(article_id: str) -> str:
    # Deterministic: re-uploading the same document overwrites its points
    # instead of accumulating duplicates.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"kb:{article_id}"))


async def upsert_to_qdrant(chunks: list[dict], qdrant_url: str):
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
    await client.upsert(collection_name=_COLLECTION, points=points)
    await client.close()


async def delete_from_qdrant(article_id: str, qdrant_url: str):
    """Delete a point by article_id payload filter."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    client = AsyncQdrantClient(url=qdrant_url)
    try:
        await client.delete(
            collection_name=_COLLECTION,
            points_selector=Filter(
                must=[FieldCondition(key="metadata.article_id", match=MatchValue(value=article_id))]
            ),
        )
    except Exception:
        pass
    await client.close()


async def process_document(text: str, chat_client: "ChatClient", openai_key: str, qdrant_url: str) -> list[dict]:
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
        await ensure_collection(qdrant_url)
        await upsert_to_qdrant(chunks, qdrant_url)
        print(f"[KB] Upserted {len(chunks)} vectors to Qdrant")
        for c in chunks:
            c.pop("embedding", None)
        return chunks
    except Exception as e:
        print(f"[KB] Exception in process_document: {e}")
        raise
