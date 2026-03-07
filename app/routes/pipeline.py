"""
Phase 9: Eval-friendly pipeline endpoints.

All endpoints are admin-only (user.is_admin required). They bypass Celery,
run pipeline stages directly, and return structured Pydantic responses for
the eval runner (leeg-eval, Phase 13) and the dashboard SSE stream.

Routes:
  POST /api/pipeline/run             — full batch pipeline, returns response + trace
  POST /api/pipeline/run-batch       — run up to 50 inputs sequentially
  POST /api/pipeline/debug/preprocess — Stage 1 only
  POST /api/pipeline/debug/rag        — Stages 1-2
  POST /api/pipeline/debug/generate   — Stages 1-3 (or controlled form: skip stages 1-2)
"""
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.db import get_db
from app.models.user import User
from app.pipeline import run_pipeline
from app.schemas.pipeline import PipelineTrace, PostprocessedResponse, StructuredInput
from app.stages.generation.agent import run_agent
from app.stages.preprocess import preprocess_input
from app.stages.retrieval import retrieve_context

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


# ── Admin guard ────────────────────────────────────────────────────────────────

def _require_admin(current_user: User) -> None:
    """Raise 403 if the authenticated user is not an admin."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )


# ── Request / Response models ─────────────────────────────────────────────────

class PipelineRunRequest(BaseModel):
    input: str
    context: dict


class PipelineRunResponse(BaseModel):
    response: PostprocessedResponse
    trace: PipelineTrace


class BatchRunRequest(BaseModel):
    inputs: list[PipelineRunRequest]


class BatchRunResponse(BaseModel):
    results: list[PipelineRunResponse]


class DebugPreprocessResponse(BaseModel):
    structured_input: StructuredInput


class DebugRagResponse(BaseModel):
    structured_input: StructuredInput
    chunks: list[dict]


class DebugGenerateRequest(BaseModel):
    # Standard form: run all three stages from raw input
    input: str | None = None
    context: dict = {}
    # Controlled form: inject pre-built stage 1-2 outputs to isolate stage 3
    structured_input: StructuredInput | None = None
    rag_context: list[dict] | None = None


class DebugGenerateResponse(BaseModel):
    answer: str
    tool_calls: list[dict]
    iterations: int
    stop_reason: str
    tokens_prompt: int = 0
    tokens_completion: int = 0


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/run", response_model=PipelineRunResponse)
async def pipeline_run(
    req: PipelineRunRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PipelineRunResponse:
    """Run all four pipeline stages and return the final response plus a full trace.

    Primary eval runner target. Always uses the batch path regardless of channel.
    """
    _require_admin(current_user)
    response, trace = await run_pipeline(req.input, req.context, db)
    return PipelineRunResponse(response=response, trace=trace)


@router.post("/run-batch", response_model=BatchRunResponse)
async def pipeline_run_batch(
    req: BatchRunRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BatchRunResponse:
    """Run up to 50 inputs sequentially. Used for bulk test-set runs in the eval runner."""
    _require_admin(current_user)
    if len(req.inputs) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 50 inputs per batch request",
        )
    results = []
    for item in req.inputs:
        response, trace = await run_pipeline(item.input, item.context, db)
        results.append(PipelineRunResponse(response=response, trace=trace))
    return BatchRunResponse(results=results)


@router.post("/debug/preprocess", response_model=DebugPreprocessResponse)
async def debug_preprocess(
    req: PipelineRunRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> DebugPreprocessResponse:
    """Stage 1 only. Returns the full StructuredInput with intent, confidence, entities,
    and guard result. Enables retrieval-independent evaluation of intent classification
    and safety guard accuracy without incurring RAG or LLM cost.
    """
    _require_admin(current_user)
    structured_input = await preprocess_input(req.input, req.context)
    return DebugPreprocessResponse(structured_input=structured_input)


@router.post("/debug/rag", response_model=DebugRagResponse)
async def debug_rag(
    req: PipelineRunRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> DebugRagResponse:
    """Stages 1-2. Returns StructuredInput plus the full ranked chunk list with
    per-chunk scores, doc_type, and entity_id. Enables descriptive and inferential
    statistics on retrieval quality without incurring LLM cost.
    """
    _require_admin(current_user)
    structured_input = await preprocess_input(req.input, req.context)
    chunks = await retrieve_context(structured_input, req.context)
    return DebugRagResponse(structured_input=structured_input, chunks=chunks)


@router.post("/debug/generate", response_model=DebugGenerateResponse)
async def debug_generate(
    req: DebugGenerateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DebugGenerateResponse:
    """Stages 1-3 (pre-post-processing). Returns the raw agent loop result.

    Accepts two forms:
    - Standard form: {"input": str, "context": dict} — runs stages 1-2 first.
    - Controlled form: {"structured_input": ..., "rag_context": [...], "context": dict}
      — injects fixed stage 1-2 outputs to isolate generation experiments
      (hold retrieval constant, vary prompt or model settings).

    Returns answer, tool_calls log, iterations, stop_reason, and token counts.
    Pre-post-processing: no PII redaction applied to the returned answer.
    """
    _require_admin(current_user)

    if req.structured_input is not None:
        # Controlled form: skip stages 1-2
        structured_input = req.structured_input
        rag_context = req.rag_context or []
    elif req.input is not None:
        structured_input = await preprocess_input(req.input, req.context)
        rag_context = await retrieve_context(structured_input, req.context)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either 'input' or 'structured_input'",
        )

    raw_output = await run_agent(structured_input, rag_context, req.context, db)

    return DebugGenerateResponse(
        answer=raw_output["answer"],
        tool_calls=raw_output["tool_calls"],
        iterations=raw_output["iterations"],
        stop_reason=raw_output["stop_reason"],
        tokens_prompt=raw_output.get("tokens_prompt", 0),
        tokens_completion=raw_output.get("tokens_completion", 0),
    )
