"""
Pydantic models shared across pipeline stages.

StructuredInput is produced by Stage 1 (preprocess) and consumed by
Stage 2 (RAG), Stage 3 (generate), and Stage 4 (postprocess).

PostprocessedResponse is produced by Stage 4 (postprocess) and consumed by
the pipeline orchestrator (Phase 9) and the SMS sender / dashboard renderer.
"""
import enum

from pydantic import BaseModel, Field


class Intent(str, enum.Enum):
    attendance_update = "attendance_update"   # "yes I'll be there" / "can't make it"
    lineup_request = "lineup_request"         # "can you set the lineup?"
    preference_update = "preference_update"   # "I prefer to play wing"
    survey_response = "survey_response"       # reply to a captain survey blast
    sub_request = "sub_request"               # "anyone want to sub Tuesday?"
    schedule_query = "schedule_query"         # "when is the next game?"
    query = "query"                           # general free-form question
    unknown = "unknown"                       # fallback / low-confidence


class EntityMap(BaseModel):
    """NER output from spaCy + custom hockey entity rules."""
    persons: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    times: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    positions: list[str] = Field(default_factory=list)   # center/wing/defense/goalie
    actions: list[str] = Field(default_factory=list)     # yes/no/maybe/out/in


class StructuredInput(BaseModel):
    """Output of Stage 1: enriched, validated, safety-checked input."""
    raw_text: str
    channel: str                          # "sms" | "dashboard"
    from_phone: str
    entities: EntityMap = Field(default_factory=EntityMap)
    intent: Intent = Intent.unknown
    is_safe: bool = True
    safety_reason: str = ""
    confidence: float = 0.0               # 0.0–1.0 intent confidence
    metadata: dict = Field(default_factory=dict)


class PostprocessedResponse(BaseModel):
    """Output of Stage 4: final validated, redacted, formatted pipeline response.

    text_for_user is the only field handed to the SMS sender or dashboard
    renderer. All other fields are for observability, tracing, and Phase 9's
    PipelineTrace (specifically: mutations → postprocess_mutations).
    """
    # Delivery payload
    text_for_user: str                                # final text to send (redacted + formatted)
    channel: str                                      # "sms" | "dashboard"

    # Audit trail (feeds PipelineTrace.postprocess_mutations in Phase 9)
    mutations: list[str] = Field(default_factory=list)  # e.g. ["pii_redacted", "truncated"]
    pii_detected: bool = False
    was_truncated: bool = False

    # Pass-through from Stage 3 (unchanged — for audit log and trace)
    tool_calls: list[dict] = Field(default_factory=list)
    iterations: int = 0
    stop_reason: str = ""

    # Dashboard channel only (None for SMS)
    dashboard_payload: dict | None = None


class PipelineTrace(BaseModel):
    """Observability trace emitted alongside PostprocessedResponse by the Phase 9 orchestrator.

    Returned by /api/pipeline/run for the eval runner; also logged to structlog for Loki ingestion.
    All fields have safe defaults — partial traces are valid when a stage short-circuits.
    """
    # Per-stage wall-clock timing (seconds)
    stage_timings: dict[str, float] = Field(default_factory=dict)

    # Redis cache hit/miss ("pipeline" key = full-pipeline cache)
    cache_hits: dict[str, bool] = Field(default_factory=dict)

    # Stage 1 guard result
    guard_result: dict = Field(default_factory=dict)

    # Stage 2 RAG metrics
    rag_chunks_retrieved: int = 0       # before re-rank
    rag_chunks_after_rerank: int = 0    # after re-rank (top-k kept)
    rag_top_scores: list[float] = Field(default_factory=list)

    # Stage 3 LLM token usage (accumulated across all agent iterations)
    llm_tokens_prompt: int = 0
    llm_tokens_completion: int = 0
    raw_llm_output: str = ""            # unredacted final answer (for eval only; not logged in full)

    # Stage 4 post-processing mutations
    postprocess_mutations: list[str] = Field(default_factory=list)
