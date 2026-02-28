"""
Pydantic models shared across pipeline stages.

StructuredInput is produced by Stage 1 (preprocess) and consumed by
Stage 2 (RAG), Stage 3 (generate), and Stage 4 (postprocess).
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
