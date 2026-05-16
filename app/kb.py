import json
import re

from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

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


async def chunk_document(text: str, openai_key: str) -> list[dict]:
    """Call GPT to split the document into KB chunks. Returns list of chunk dicts."""
    client = AsyncOpenAI(api_key=openai_key)
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": _CHUNKING_PROMPT},
            {"role": "user",   "content": text},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content
    # GPT may return {"chunks": [...]} or just [...]
    parsed = json.loads(raw)
    chunks = parsed if isinstance(parsed, list) else parsed.get("chunks", list(parsed.values())[0])

    # Ensure unique slugs — use GPT's id if valid, else derive from title
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
    """Add 'embedding' field to each chunk. Sends in batches of _BATCH_SIZE."""
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


async def ensure_collection(qdrant_url: str):
    """Create Qdrant collection if it doesn't exist."""
    client = AsyncQdrantClient(url=qdrant_url)
    try:
        await client.get_collection(_COLLECTION)
    except Exception:
        await client.create_collection(
            _COLLECTION,
            vectors_config=VectorParams(size=_EMBED_DIMS, distance=Distance.COSINE),
        )
    await client.close()


async def upsert_to_qdrant(chunks: list[dict], qdrant_url: str):
    """Upsert embedded chunks into Qdrant."""
    client = AsyncQdrantClient(url=qdrant_url)
    points = [
        PointStruct(
            id=abs(hash(c["id"])) % (2**63),
            vector=c["embedding"],
            payload={
                "article_id": c["id"],
                "title":      c["title"],
                "category":   c["category"],
                "keywords":   c["keywords"],
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
                must=[FieldCondition(key="article_id", match=MatchValue(value=article_id))]
            ),
        )
    except Exception:
        pass
    await client.close()


async def process_document(text: str, openai_key: str, qdrant_url: str) -> list[dict]:
    """Full pipeline: text → chunks → embeddings → qdrant. Returns chunks (without embeddings)."""
    print(f"[KB] Chunking document ({len(text)} chars)...")
    chunks = await chunk_document(text, openai_key)
    print(f"[KB] Created {len(chunks)} chunks, embedding...")
    chunks = await embed_chunks(chunks, openai_key)
    await ensure_collection(qdrant_url)
    await upsert_to_qdrant(chunks, qdrant_url)
    print(f"[KB] Upserted {len(chunks)} vectors to Qdrant")
    for c in chunks:
        c.pop("embedding", None)
    return chunks
