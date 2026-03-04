"""
RAG Stage 2: Hybrid retrieval from Qdrant.

Given a natural-language query and context (must include team_id), returns
the top-k most relevant document chunks from the leeg_docs collection.

Filtering:
  - Always filters by team_id (security: captains only see their own data)
  - Optional doc_type filter (e.g. only "player" docs for lineup queries)

Redis cache:
  key = "rag:<sha256(query + team_id + doc_type_filter)>"
  TTL = 60s (short -- roster/game data changes frequently)

All qdrant_client imports are lazy so this module is importable without the
package installed.
"""
import hashlib
import json
import logging

import redis.asyncio as aioredis

from app.config import settings
from app.rag.embeddings import embed_query
from app.rag.ingestion import COLLECTION_NAME

log = logging.getLogger(__name__)

_CACHE_TTL = 60  # seconds
_CACHE_PREFIX = "rag:"


def _cache_key(query: str, team_id: int, doc_types: list[str] | None) -> str:
    raw = f"{query}|{team_id}|{sorted(doc_types) if doc_types else ''}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"{_CACHE_PREFIX}{digest}"


def _get_qdrant():
    from qdrant_client import AsyncQdrantClient  # lazy
    return AsyncQdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)


async def retrieve(
    query: str,
    context: dict,
    top_k: int = 10,
    doc_types: list[str] | None = None,
) -> list[dict]:
    """Retrieve top-k relevant chunks for a query from this team's data.

    Args:
        query:     Natural-language search query.
        context:   Must contain "team_id" (int).
        top_k:     Number of results to return before re-ranking.
        doc_types: Optional list of doc_type values to filter.

    Returns:
        List of dicts: [{text, score, team_id, doc_type, entity_id, chunk_idx}]
    """
    from qdrant_client.models import FieldCondition, Filter, MatchValue  # lazy

    team_id: int = context.get("team_id", 0)

    # ── Cache check ───────────────────────────────────────────────────────────
    redis = None
    cache_key = _cache_key(query, team_id, doc_types)
    try:
        redis = await aioredis.from_url(settings.redis_url, decode_responses=True)
        cached = await redis.get(cache_key)
        if cached:
            log.debug("retriever.cache_hit team_id=%d", team_id)
            await redis.aclose()
            return json.loads(cached)
    except Exception as exc:
        log.warning("retriever.cache.unavailable: %s", exc)

    # ── Build Qdrant filter ───────────────────────────────────────────────────
    if doc_types:
        qdrant_filter = Filter(
            must=[FieldCondition(key="team_id", match=MatchValue(value=team_id))],
            should=[
                FieldCondition(key="doc_type", match=MatchValue(value=dt))
                for dt in doc_types
            ],
        )
    else:
        qdrant_filter = Filter(
            must=[FieldCondition(key="team_id", match=MatchValue(value=team_id))]
        )

    # ── Embed query ───────────────────────────────────────────────────────────
    query_vector = await embed_query(query)

    # ── Search Qdrant ─────────────────────────────────────────────────────────
    client = _get_qdrant()
    try:
        hits = await client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True,
        )
    finally:
        await client.close()

    results = [
        {
            "text": hit.payload.get("text", ""),
            "score": hit.score,
            "team_id": hit.payload.get("team_id"),
            "doc_type": hit.payload.get("doc_type"),
            "entity_id": hit.payload.get("entity_id"),
            "chunk_idx": hit.payload.get("chunk_idx", 0),
        }
        for hit in hits
    ]

    # ── Cache results ─────────────────────────────────────────────────────────
    if redis is not None:
        try:
            await redis.set(cache_key, json.dumps(results), ex=_CACHE_TTL)
        except Exception as exc:
            log.warning("retriever.cache.write_failed: %s", exc)
        await redis.aclose()

    log.info(
        "retriever.done team_id=%d query=%r results=%d",
        team_id,
        query[:60],
        len(results),
    )
    return results
