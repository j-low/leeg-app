"""
Stage 2: Hybrid RAG -- retrieve, re-rank, and compress context.

Pipeline:
  1. retrieve()   -- Qdrant dense search + Redis cache (top 10 candidates)
  2. rerank()     -- Cross-encoder re-scoring, keep top 5
  3. LLMLingua    -- Token compression (~50% reduction, key facts preserved)

Short-circuits (returns []) for intents that never need grounding:
  - attendance_update  (plain yes/no; no roster lookup needed)

The compressed context chunks returned here are passed directly into the
prompt assembly in Stage 3 (generation/prompts.py).
"""
import logging

import structlog

from app.rag.retriever import retrieve
from app.rag.reranker import rerank
from app.schemas.pipeline import Intent, StructuredInput

log = structlog.get_logger(__name__)

# Intents that don't need document grounding
_NO_RAG_INTENTS = {Intent.attendance_update}

# LLMLingua compression ratio (0.5 = keep ~50% of tokens)
_COMPRESSION_RATIO = 0.5


def _try_import_llmlingua():
    """Lazy import so tests can run without llmlingua installed."""
    try:
        from llmlingua import PromptCompressor
        return PromptCompressor
    except ImportError:
        return None


async def retrieve_context(
    structured_input: StructuredInput,
    context: dict,
) -> list[dict]:
    """Stage 2 entry point: retrieve and compress context for Stage 3.

    Args:
        structured_input: Output of Stage 1 (preprocess).
        context:          Pipeline context dict; must include 'team_id'.

    Returns:
        List of compressed context chunk dicts [{text, score, doc_type, ...}].
        Empty list if intent does not require grounding.
    """
    # Skip RAG for intents that don't benefit from document context
    if structured_input.intent in _NO_RAG_INTENTS:
        log.info("rag.skipped intent=%s", structured_input.intent)
        return []

    query = structured_input.raw_text

    # ── Retrieve ──────────────────────────────────────────────────────────────
    candidates = await retrieve(query, context, top_k=10)
    if not candidates:
        log.info("rag.no_results query=%r", query[:60])
        return []

    # ── Re-rank ───────────────────────────────────────────────────────────────
    reranked = await rerank(query, candidates, top_k=5)

    # ── LLMLingua compression ─────────────────────────────────────────────────
    PromptCompressor = _try_import_llmlingua()
    if PromptCompressor is not None:
        try:
            # Combine chunk texts into a single context block for compression
            combined = "\n\n".join(c["text"] for c in reranked)
            compressor = PromptCompressor(
                model_name="openai-community/gpt2",  # lightweight local model for compression
                use_llmlingua2=False,
                device_map="cpu",
            )
            result = compressor.compress_prompt(
                context=[combined],
                ratio=_COMPRESSION_RATIO,
                force_tokens=["\n"],
            )
            compressed_text = result.get("compressed_prompt", combined)

            # Re-wrap into a single chunk dict so Stage 3 can iterate uniformly
            reranked = [{
                "text": compressed_text,
                "score": reranked[0]["score"] if reranked else 1.0,
                "doc_type": "compressed",
                "compressed": True,
                "original_chunks": len(reranked),
            }]
            log.info(
                "rag.compressed ratio=%s original_len=%d compressed_len=%d",
                _COMPRESSION_RATIO,
                len(combined),
                len(compressed_text),
            )
        except Exception as exc:
            log.warning("rag.compression_failed falling back to uncompressed: %s", exc)
    else:
        log.debug("rag.llmlingua_unavailable using uncompressed chunks")

    log.info(
        "rag.done intent=%s chunks=%d",
        structured_input.intent,
        len(reranked),
    )
    return reranked
