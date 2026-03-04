"""
RAG Stage 2: Text embedding utility.

Uses sentence-transformers (all-MiniLM-L6-v2) for dense vector generation.
The model is loaded once at first call and reused across all requests.

Redis caching:
  key = "emb:<sha256(text)>"
  value = JSON-serialised float list
  TTL = 24 hours

All ML imports (sentence-transformers) are lazy so this module is importable
in environments where the packages are not installed (e.g. CI for other stages).
"""
import asyncio
import hashlib
import json
import logging

import redis.asyncio as aioredis

from app.config import settings

log = logging.getLogger(__name__)

# ── Model (loaded once on first call) ─────────────────────────────────────────
_MODEL_NAME = "all-MiniLM-L6-v2"
_model = None  # SentenceTransformer instance, lazy-loaded


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer  # lazy import
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


# ── Redis cache helpers ───────────────────────────────────────────────────────
_CACHE_TTL = 86_400  # 24 hours
_CACHE_PREFIX = "emb:"


def _cache_key(text: str) -> str:
    digest = hashlib.sha256(text.encode()).hexdigest()
    return f"{_CACHE_PREFIX}{digest}"


async def _get_redis() -> aioredis.Redis:
    return await aioredis.from_url(settings.redis_url, decode_responses=True)


# ── Public API ────────────────────────────────────────────────────────────────

async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts, using Redis cache where available."""
    if not texts:
        return []

    results: list[list[float] | None] = [None] * len(texts)
    uncached_indices: list[int] = []
    uncached_texts: list[str] = []
    redis = None

    try:
        redis = await _get_redis()
        keys = [_cache_key(t) for t in texts]
        cached = await redis.mget(*keys)

        for i, (value, text) in enumerate(zip(cached, texts)):
            if value is not None:
                results[i] = json.loads(value)
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)
    except Exception as exc:
        log.warning("embeddings.cache.unavailable: %s", exc)
        uncached_indices = list(range(len(texts)))
        uncached_texts = list(texts)
        redis = None

    if uncached_texts:
        model = _get_model()
        vectors: list[list[float]] = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: model.encode(uncached_texts, convert_to_numpy=True).tolist(),
        )
        for idx, vector in zip(uncached_indices, vectors):
            results[idx] = vector

        if redis is not None:
            try:
                pipe = redis.pipeline()
                for text, vector in zip(uncached_texts, vectors):
                    pipe.set(_cache_key(text), json.dumps(vector), ex=_CACHE_TTL)
                await pipe.execute()
            except Exception as exc:
                log.warning("embeddings.cache.write_failed: %s", exc)

    if redis is not None:
        await redis.aclose()
    return [r for r in results if r is not None]


async def embed_query(query: str) -> list[float]:
    """Convenience wrapper for single-query embedding."""
    vectors = await embed_texts([query])
    return vectors[0]
