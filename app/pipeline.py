"""
Phase 9: Pipeline orchestrator — chains all four AI stages with channel-aware
dual-mode execution, Redis caching, per-stage timeouts, and OTel/Prometheus
observability.

Batch path   (run_pipeline)        — SMS inbound + eval endpoints
Streaming path (run_pipeline_stream) — dashboard SSE channel only

Both paths never raise: all exceptions are caught and converted to safe
fallback responses / error events.
"""
import asyncio
import hashlib
import time
from collections.abc import AsyncGenerator

import structlog

from app.config import settings
from app.observability import LLM_TOKENS, PIPELINE_DURATION, PIPELINE_ERRORS, STAGE_DURATION, get_tracer
from app.schemas.pipeline import PipelineTrace, PostprocessedResponse, StructuredInput
from app.stages.generation.agent import run_agent, stream_agent
from app.stages.postprocess import postprocess
from app.stages.preprocess import SecurityError, preprocess_input
from app.stages.retrieval import retrieve_context

log = structlog.get_logger(__name__)
tracer = get_tracer()

# Per-stage asyncio timeout limits (seconds)
_TIMEOUTS = {
    "preprocess":  5.0,
    "rag":        10.0,
    "generate":  120.0,
    "postprocess": 5.0,
}

_CACHE_TTL = 60  # seconds — full pipeline result cache TTL

_SAFETY_FALLBACK_TEXT = "Sorry, I can't help with that."
_ERROR_FALLBACK_TEXT  = "Sorry, something went wrong. Please try again."


# ── Redis helpers ──────────────────────────────────────────────────────────────

async def _get_redis():
    """Return a connected redis.asyncio client, or None if Redis is unavailable.

    Fail-open: if Redis is down the pipeline runs without caching.
    """
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(settings.redis_url, socket_connect_timeout=1.0)
        await client.ping()
        return client
    except Exception:
        return None


def _cache_key(raw_input: str, context: dict) -> str:
    payload = f"{raw_input}:{context.get('team_id')}:{context.get('channel')}"
    return f"pipeline:v1:{hashlib.sha256(payload.encode()).hexdigest()}"


# ── Batch pipeline ─────────────────────────────────────────────────────────────

async def run_pipeline(
    raw_input: str,
    context: dict,
    db,
) -> tuple[PostprocessedResponse, PipelineTrace]:
    """Execute the full AI pipeline in batch mode.

    Chain: preprocess → retrieve_context → run_agent → postprocess.

    Used by: SMS inbound webhook, /api/pipeline/run eval endpoint.
    Never raises — returns a safe fallback PostprocessedResponse on any error.

    Args:
        raw_input: Raw text from SMS or eval request.
        context:   Dict with channel, team_id, from_phone, etc.
        db:        Active AsyncSession for tool DB access.

    Returns:
        (PostprocessedResponse, PipelineTrace)
    """
    channel = context.get("channel", "sms")
    pipeline_start = time.monotonic()
    trace_data = PipelineTrace()
    structured_input: StructuredInput | None = None
    raw_output: dict = {}

    with tracer.start_as_current_span("pipeline.batch") as span:
        span.set_attribute("channel", channel)
        span.set_attribute("team_id", str(context.get("team_id", "")))

        try:
            # ── Redis cache check ──────────────────────────────────────────────
            redis = await _get_redis()
            cache_key = _cache_key(raw_input, context)
            if redis:
                try:
                    cached = await redis.get(cache_key)
                    if cached:
                        trace_data.cache_hits["pipeline"] = True
                        trace_data.stage_timings["total"] = time.monotonic() - pipeline_start
                        log.info("pipeline.batch.cache_hit", channel=channel)
                        return PostprocessedResponse.model_validate_json(cached), trace_data
                except Exception:
                    pass
            trace_data.cache_hits["pipeline"] = False

            # ── Stage 1: Preprocess ────────────────────────────────────────────
            with tracer.start_as_current_span("stage.preprocess"):
                t0 = time.monotonic()
                try:
                    structured_input = await asyncio.wait_for(
                        preprocess_input(raw_input, context),
                        timeout=_TIMEOUTS["preprocess"],
                    )
                except asyncio.TimeoutError:
                    PIPELINE_ERRORS.labels(stage="preprocess").inc()
                    log.error("pipeline.preprocess.timeout")
                    trace_data.stage_timings["preprocess"] = time.monotonic() - t0
                    STAGE_DURATION.labels(stage="preprocess").observe(trace_data.stage_timings["preprocess"])
                    return _fallback(channel, "timeout:preprocess"), trace_data
                except SecurityError as exc:
                    trace_data.guard_result = {"is_safe": False, "reason": exc.reason}
                    trace_data.stage_timings["preprocess"] = time.monotonic() - t0
                    STAGE_DURATION.labels(stage="preprocess").observe(trace_data.stage_timings["preprocess"])
                    log.info("pipeline.preprocess.security_error", reason=exc.reason)
                    return _safety_fallback(channel), trace_data

                elapsed = time.monotonic() - t0
                trace_data.stage_timings["preprocess"] = elapsed
                STAGE_DURATION.labels(stage="preprocess").observe(elapsed)

            trace_data.guard_result = {
                "is_safe":    structured_input.is_safe,
                "reason":     structured_input.safety_reason,
                "intent":     str(structured_input.intent),
                "confidence": structured_input.confidence,
            }

            if not structured_input.is_safe:
                return _safety_fallback(channel), trace_data

            # ── Stage 2: RAG ───────────────────────────────────────────────────
            with tracer.start_as_current_span("stage.rag"):
                t0 = time.monotonic()
                try:
                    rag_chunks = await asyncio.wait_for(
                        retrieve_context(structured_input, context),
                        timeout=_TIMEOUTS["rag"],
                    )
                except asyncio.TimeoutError:
                    PIPELINE_ERRORS.labels(stage="rag").inc()
                    log.warning("pipeline.rag.timeout — continuing with empty context")
                    rag_chunks = []
                elapsed = time.monotonic() - t0
                trace_data.stage_timings["rag"] = elapsed
                STAGE_DURATION.labels(stage="rag").observe(elapsed)

            trace_data.rag_chunks_retrieved = len(rag_chunks)
            trace_data.rag_chunks_after_rerank = len(rag_chunks)
            trace_data.rag_top_scores = [c.get("score", 0.0) for c in rag_chunks[:5]]

            # ── Stage 3: Generate ──────────────────────────────────────────────
            with tracer.start_as_current_span("stage.generate"):
                t0 = time.monotonic()
                try:
                    raw_output = await asyncio.wait_for(
                        run_agent(structured_input, rag_chunks, context, db),
                        timeout=_TIMEOUTS["generate"],
                    )
                except asyncio.TimeoutError:
                    PIPELINE_ERRORS.labels(stage="generate").inc()
                    log.error("pipeline.generate.timeout")
                    elapsed = time.monotonic() - t0
                    trace_data.stage_timings["generate"] = elapsed
                    STAGE_DURATION.labels(stage="generate").observe(elapsed)
                    return _fallback(channel, "timeout:generate"), trace_data
                elapsed = time.monotonic() - t0
                trace_data.stage_timings["generate"] = elapsed
                STAGE_DURATION.labels(stage="generate").observe(elapsed)

            trace_data.llm_tokens_prompt = raw_output.get("tokens_prompt", 0)
            trace_data.llm_tokens_completion = raw_output.get("tokens_completion", 0)
            trace_data.raw_llm_output = raw_output.get("answer", "")
            LLM_TOKENS.labels(type="prompt").inc(trace_data.llm_tokens_prompt)
            LLM_TOKENS.labels(type="completion").inc(trace_data.llm_tokens_completion)

            # ── Stage 4: Postprocess ───────────────────────────────────────────
            with tracer.start_as_current_span("stage.postprocess"):
                t0 = time.monotonic()
                try:
                    response = await asyncio.wait_for(
                        postprocess(raw_output, context, structured_input),
                        timeout=_TIMEOUTS["postprocess"],
                    )
                except asyncio.TimeoutError:
                    PIPELINE_ERRORS.labels(stage="postprocess").inc()
                    log.error("pipeline.postprocess.timeout")
                    elapsed = time.monotonic() - t0
                    trace_data.stage_timings["postprocess"] = elapsed
                    STAGE_DURATION.labels(stage="postprocess").observe(elapsed)
                    return _fallback(channel, "timeout:postprocess"), trace_data
                elapsed = time.monotonic() - t0
                trace_data.stage_timings["postprocess"] = elapsed
                STAGE_DURATION.labels(stage="postprocess").observe(elapsed)

            trace_data.postprocess_mutations = response.mutations

            # ── Cache result ───────────────────────────────────────────────────
            if redis:
                try:
                    await redis.setex(cache_key, _CACHE_TTL, response.model_dump_json())
                except Exception:
                    pass

            total = time.monotonic() - pipeline_start
            trace_data.stage_timings["total"] = total
            PIPELINE_DURATION.labels(channel=channel).observe(total)

            log.info(
                "pipeline.batch.done",
                channel=channel,
                intent=str(structured_input.intent) if structured_input else "unknown",
                total_secs=round(total, 3),
                iterations=raw_output.get("iterations", 0),
                cache_hit=False,
            )

            return response, trace_data

        except Exception as exc:
            PIPELINE_ERRORS.labels(stage="pipeline").inc()
            log.error("pipeline.batch.failed", error=str(exc), channel=channel)
            trace_data.stage_timings["total"] = time.monotonic() - pipeline_start
            return _fallback(channel, "exception"), trace_data


# ── Streaming pipeline ─────────────────────────────────────────────────────────

async def run_pipeline_stream(
    raw_input: str,
    context: dict,
    db,
) -> AsyncGenerator[dict, None]:
    """Execute the AI pipeline in streaming mode for the dashboard SSE channel.

    Stages 1–2 run synchronously (no caching). Stage 3 streams events via
    stream_agent(). Stage 4 (PII redaction + formatting) is applied to the
    accumulated answer and emitted as the final "done" event.

    Yields typed event dicts:
        {type: "answer_token", text: str}
        {type: "tool_start",   name: str, input: dict}
        {type: "tool_result",  name: str, result: any}
        {type: "done",   text_for_user: str, mutations: list[str]}
        {type: "error",  message: str}   (on unhandled failure; never raises)
    """
    channel = context.get("channel", "dashboard")
    structured_input: StructuredInput | None = None

    try:
        # ── Stage 1: Preprocess ────────────────────────────────────────────────
        try:
            structured_input = await asyncio.wait_for(
                preprocess_input(raw_input, context),
                timeout=_TIMEOUTS["preprocess"],
            )
        except SecurityError:
            yield {"type": "done", "text_for_user": _SAFETY_FALLBACK_TEXT, "mutations": ["fallback:safety_rejection"]}
            return
        except asyncio.TimeoutError:
            yield {"type": "error", "message": "Preprocessing timed out."}
            return

        if not structured_input.is_safe:
            yield {"type": "done", "text_for_user": _SAFETY_FALLBACK_TEXT, "mutations": ["fallback:safety_rejection"]}
            return

        # ── Stage 2: RAG ───────────────────────────────────────────────────────
        try:
            rag_chunks = await asyncio.wait_for(
                retrieve_context(structured_input, context),
                timeout=_TIMEOUTS["rag"],
            )
        except asyncio.TimeoutError:
            log.warning("pipeline.stream.rag.timeout — continuing with empty context")
            rag_chunks = []

        # ── Stage 3: Stream generation ─────────────────────────────────────────
        accumulated_answer = ""
        async for event in stream_agent(structured_input, rag_chunks, context, db):
            yield event
            if event.get("type") == "answer_token":
                accumulated_answer += event.get("text", "")

        # ── Stage 4: Postprocess accumulated answer ────────────────────────────
        raw_output = {
            "answer":      accumulated_answer,
            "tool_calls":  [],
            "iterations":  0,
            "stop_reason": "end_turn",
        }
        response = await asyncio.wait_for(
            postprocess(raw_output, context, structured_input),
            timeout=_TIMEOUTS["postprocess"],
        )

        yield {
            "type":          "done",
            "text_for_user": response.text_for_user,
            "mutations":     response.mutations,
        }

    except Exception as exc:
        log.error("pipeline.stream.failed", error=str(exc), channel=channel)
        yield {"type": "error", "message": _ERROR_FALLBACK_TEXT}


# ── Fallback helpers ───────────────────────────────────────────────────────────

def _fallback(channel: str, reason: str) -> PostprocessedResponse:
    return PostprocessedResponse(
        text_for_user=_ERROR_FALLBACK_TEXT,
        channel=channel,
        mutations=[f"fallback:{reason}"],
        stop_reason=reason,
    )


def _safety_fallback(channel: str) -> PostprocessedResponse:
    return PostprocessedResponse(
        text_for_user=_SAFETY_FALLBACK_TEXT,
        channel=channel,
        mutations=["fallback:safety_rejection"],
        stop_reason="safety",
    )
