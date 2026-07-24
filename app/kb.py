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


def collection_name(service_slug: str) -> str:
    """One Qdrant collection per VPN brand.

    The n8n AI Agent must point its Vector Store at the same name and use the
    same embedding model as _EMBED_MODEL, otherwise retrieval returns noise.
    """
    return f"kb_{service_slug}"


def article_id(service_slug: str, chunk_slug: str) -> str:
    """KB article ids are shared across services in one table — scope them."""
    return f"{service_slug}:{chunk_slug}"


def _point_id(article: str) -> str:
    # uuid5, not hash(): Python salts string hashing per process, so the same
    # chunk re-uploaded from a restarted worker used to land on a new point and
    # leave a duplicate behind.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, article))

_CHUNKING_PROMPT = """You are a knowledge base indexing assistant. Your task is to parse the provided support documentation and split it into semantically meaningful, self-contained chunks suitable for vector search.

## RULES FOR CHUNKING

Each chunk must:
- Cover ONE specific topic or scenario (e.g., one device setup, one FAQ item, one troubleshooting branch)
- Be self-contained — readable and useful WITHOUT context from other chunks
- Include relevant keywords a user might actually type (in Russian and English)
- Be 100–400 words maximum

## OUTPUT FORMAT

Return a JSON array. Each element is an object:

{
  "id": "unique_slug",
  "category": "troubleshooting | setup | payment | faq | escalation",
  "title": "Short descriptive title",
  "keywords": ["keyword1", "keyword2", ...],
  "content": "Full self-contained text of this chunk"
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


def _make_slug(title: str, existing: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower().strip())[:60].strip("-") or "chunk"
    slug = base
    i = 2
    while slug in existing:
        slug = f"{base}-{i}"
        i += 1
    existing.add(slug)
    return slug


async def chunk_document(text: str, chat_client: "ChatClient") -> list[dict]:
    """Call the configured chat LLM to split the document into KB chunks."""
    response = await chat_client.client.chat.completions.create(
        model=chat_client.model,
        messages=[
            {"role": "system", "content": _CHUNKING_PROMPT},
            {"role": "user",   "content": text},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content
    parsed = json.loads(raw)
    chunks = parsed if isinstance(parsed, list) else parsed.get("chunks", list(parsed.values())[0])

    seen: set[str] = set()
    result = []
    for c in chunks:
        slug = _make_slug(c.get("id") or c.get("title", "chunk"), seen)
        result.append({
            "id":       slug,
            "title":    c.get("title", ""),
            "category": c.get("category", "faq"),
            "keywords": c.get("keywords", []),
            "content":  c.get("content", ""),
        })
    return result


async def embed_chunks(chunks: list[dict], openai_key: str) -> list[dict]:
    """Embed chunks using OpenAI text-embedding-3-small (always OpenAI)."""
    client = AsyncOpenAI(api_key=openai_key)
    texts = [c["content"] for c in chunks]
    embeddings = []
    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i: i + _BATCH_SIZE]
        resp = await client.embeddings.create(model=_EMBED_MODEL, input=batch)
        embeddings.extend([item.embedding for item in resp.data])
    for chunk, emb in zip(chunks, embeddings):
        chunk["embedding"] = emb
    return chunks


async def ensure_collection(qdrant_url: str, collection: str):
    """Create Qdrant collection if it doesn't exist."""
    client = AsyncQdrantClient(url=qdrant_url)
    try:
        await client.get_collection(collection)
    except Exception:
        await client.create_collection(
            collection,
            vectors_config=VectorParams(size=_EMBED_DIMS, distance=Distance.COSINE),
        )
    await client.close()


async def upsert_to_qdrant(chunks: list[dict], qdrant_url: str, collection: str):
    """Upsert embedded chunks into Qdrant."""
    client = AsyncQdrantClient(url=qdrant_url)
    points = [
        PointStruct(
            id=_point_id(c["id"]),
            vector=c["embedding"],
            payload={
                "article_id": c["id"],
                "title":      c["title"],
                "category":   c["category"],
                "keywords":   c["keywords"],
                # n8n's Vector Store returns the payload, not the vector —
                # without the text the AI Agent has nothing to quote.
                "content":    c["content"],
            },
        )
        for c in chunks
    ]
    await client.upsert(collection_name=collection, points=points)
    await client.close()


async def delete_from_qdrant(article: str, qdrant_url: str, collection: str):
    """Delete a point by article_id payload filter."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    client = AsyncQdrantClient(url=qdrant_url)
    try:
        await client.delete(
            collection_name=collection,
            points_selector=Filter(
                must=[FieldCondition(key="article_id", match=MatchValue(value=article))]
            ),
        )
    except Exception:
        pass
    await client.close()


async def process_document(
    text: str, chat_client: "ChatClient", openai_key: str, qdrant_url: str, service_slug: str,
) -> list[dict]:
    """Full pipeline: text → chunks (via chat LLM) → embeddings (OpenAI) → Qdrant."""
    collection = collection_name(service_slug)
    print(f"[KB] Chunking document ({len(text)} chars) via {chat_client.model}...")
    chunks = await chunk_document(text, chat_client)
    for c in chunks:
        c["id"] = article_id(service_slug, c["id"])
    print(f"[KB] Created {len(chunks)} chunks, embedding...")
    chunks = await embed_chunks(chunks, openai_key)
    await ensure_collection(qdrant_url, collection)
    await upsert_to_qdrant(chunks, qdrant_url, collection)
    print(f"[KB] Upserted {len(chunks)} vectors into {collection}")
    for c in chunks:
        c.pop("embedding", None)
    return chunks
