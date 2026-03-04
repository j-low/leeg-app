"""
RAG Stage 2: Cross-encoder re-ranking.

After vector retrieval returns top-k candidates, this module re-scores each
(query, chunk) pair with a cross-encoder -- more accurate than cosine
similarity alone because it attends to both texts jointly.

Model: cross-encoder/ms-marco-MiniLM-L-6-v2 (~22MB, CPU-friendly)

All ML imports (sentence-transformers CrossEncoder) are lazy so this module
is importable without the package installed.
"""
import asyncio
import logging

log = logging.getLogger(__name__)

_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_reranker = None  # CrossEncoder instance, lazy-loaded


def _get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder  # lazy import
        _reranker = CrossEncoder(_RERANKER_MODEL)
    return _reranker


def _sync_rerank(query: str, chunks: list[dict], top_k: int) -> list[dict]:
    """CPU-bound re-scoring -- called inside run_in_executor."""
    if not chunks:
        return []
    reranker = _get_reranker()
    pairs = [(query, chunk["text"]) for chunk in chunks]
    scores: list[float] = reranker.predict(pairs).tolist()

    for chunk, score in zip(chunks, scores):
        chunk["rerank_score"] = score

    ranked = sorted(chunks, key=lambda c: c["rerank_score"], reverse=True)
    return ranked[:top_k]


async def rerank(query: str, chunks: list[dict], top_k: int = 5) -> list[dict]:
    """Re-rank retrieved chunks by cross-encoder score.

    Args:
        query:  The original user query.
        chunks: Output from retriever.retrieve() -- list of {text, score, ...}.
        top_k:  How many chunks to keep after re-ranking.

    Returns:
        Top-k chunks sorted by re-rank score descending; adds 'rerank_score' field.
    """
    if not chunks:
        return []

    loop = asyncio.get_event_loop()
    reranked = await loop.run_in_executor(
        None,
        _sync_rerank,
        query,
        list(chunks),  # copy so we don't mutate caller's list
        top_k,
    )

    log.info(
        "reranker.done query=%r input=%d output=%d top_score=%.3f",
        query[:60],
        len(chunks),
        len(reranked),
        reranked[0]["rerank_score"] if reranked else 0.0,
    )
    return reranked
