"""
Stage 1: Preprocessing & NER.

Transforms raw SMS / dashboard text into a StructuredInput:
  - spaCy en_core_web_sm for standard NER (PERSON, DATE, TIME, LOC)
  - Custom EntityRuler phrases for hockey-specific terms
  - Keyword + entity-based intent classification (no LLM needed)
  - Safety guard integration (guards.py)

Raises SecurityError if the safety check fails so the pipeline can
short-circuit and log the rejection without calling the LLM.
"""
import spacy
import structlog
from spacy.language import Language

from app.schemas.pipeline import EntityMap, Intent, StructuredInput
from app.stages.guards import check_safety

log = structlog.get_logger(__name__)


class SecurityError(Exception):
    """Raised when the input fails a safety guard check."""
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


# ── spaCy pipeline setup ──────────────────────────────────────────────────────

def _build_nlp() -> Language:
    nlp = spacy.load("en_core_web_sm", disable=["lemmatizer"])

    # Add custom hockey entity patterns before the standard NER component
    ruler = nlp.add_pipe("entity_ruler", before="ner", config={"overwrite_ents": False})
    ruler.add_patterns([  # type: ignore[attr-defined]
        # Positions
        {"label": "HOCKEY_POSITION", "pattern": "center"},
        {"label": "HOCKEY_POSITION", "pattern": "wing"},
        {"label": "HOCKEY_POSITION", "pattern": "left wing"},
        {"label": "HOCKEY_POSITION", "pattern": "right wing"},
        {"label": "HOCKEY_POSITION", "pattern": "defense"},
        {"label": "HOCKEY_POSITION", "pattern": "defence"},
        {"label": "HOCKEY_POSITION", "pattern": "d-man"},
        {"label": "HOCKEY_POSITION", "pattern": "forward"},
        {"label": "HOCKEY_POSITION", "pattern": "goalie"},
        {"label": "HOCKEY_POSITION", "pattern": "goaltender"},
        # Attendance actions
        {"label": "ATTENDANCE_YES",  "pattern": "in"},
        {"label": "ATTENDANCE_YES",  "pattern": "yes"},
        {"label": "ATTENDANCE_YES",  "pattern": "yeah"},
        {"label": "ATTENDANCE_YES",  "pattern": "yep"},
        {"label": "ATTENDANCE_YES",  "pattern": "confirmed"},
        {"label": "ATTENDANCE_YES",  "pattern": "attending"},
        {"label": "ATTENDANCE_NO",   "pattern": "no"},
        {"label": "ATTENDANCE_NO",   "pattern": "out"},
        {"label": "ATTENDANCE_NO",   "pattern": "can't make it"},
        {"label": "ATTENDANCE_NO",   "pattern": "cannot make it"},
        {"label": "ATTENDANCE_NO",   "pattern": "not coming"},
    ])
    return nlp


# Load once at module import; reused across all requests.
_nlp: Language = _build_nlp()


# ── Intent classification ─────────────────────────────────────────────────────

import string as _string

_TOKENS_ATTENDANCE_YES = {"yes", "yeah", "yep", "in", "coming", "attending", "confirmed", "there"}
_TOKENS_ATTENDANCE_NO  = {"no", "nope", "out", "missing", "absent", "injured", "sick",
                          "cant", "cannot"}  # "can't" → "cant" after punctuation strip
_TOKENS_ATTEND_MAYBE   = {"maybe", "might", "unsure", "possibly"}
_TOKENS_SUB            = {"sub", "substitute", "substitution", "replacement", "replace", "filling"}
_TOKENS_LINEUP         = {"lineup", "lines", "line", "formation"}
_TOKENS_PREFERENCE     = {"prefer", "preference", "want", "like", "play"}
_TOKENS_SCHEDULE       = {"when", "schedule", "date", "time", "next", "game"}

_STRIP_PUNCT = str.maketrans("", "", _string.punctuation)

_NO_ACTIONS  = {"no", "out", "can't make it", "cannot make it", "not coming"}
_YES_ACTIONS = {"yes", "in"}


def _classify_intent(
    text: str,
    entities: EntityMap,
) -> tuple[Intent, float]:
    """Keyword + entity-based intent classification. No LLM required."""
    # Strip punctuation before splitting so "maybe," == "maybe", "can't" == "cant"
    tokens = set(text.lower().translate(_STRIP_PUNCT).split())

    if tokens & _TOKENS_SUB:
        return Intent.sub_request, 0.9

    if tokens & _TOKENS_LINEUP:
        return Intent.lineup_request, 0.85

    has_yes = bool(tokens & _TOKENS_ATTENDANCE_YES or
                   any(a in _YES_ACTIONS for a in entities.actions))
    has_no  = bool(tokens & _TOKENS_ATTENDANCE_NO or
                   any(a in _NO_ACTIONS for a in entities.actions))

    if has_yes or has_no:
        return Intent.attendance_update, 0.85

    if tokens & _TOKENS_ATTEND_MAYBE:
        return Intent.attendance_update, 0.65

    if entities.positions or tokens & _TOKENS_PREFERENCE:
        return Intent.preference_update, 0.75

    if tokens & _TOKENS_SCHEDULE:
        return Intent.schedule_query, 0.80

    return Intent.query, 0.50


# ── Public API ────────────────────────────────────────────────────────────────

async def preprocess_input(raw_text: str, context: dict) -> StructuredInput:
    """Stage 1 entry point: NER → intent → safety → StructuredInput.

    Args:
        raw_text: Raw SMS body or dashboard chat message.
        context:  Dict with at minimum {"channel": ..., "from_phone": ...}.

    Returns:
        StructuredInput with all fields populated.

    Raises:
        SecurityError: if the safety guard rejects the input.
    """
    doc = _nlp(raw_text)

    # Collect entities from both standard NER and the custom ruler
    entities = EntityMap(
        persons=[e.text for e in doc.ents if e.label_ == "PERSON"],
        dates=[e.text for e in doc.ents if e.label_ in ("DATE",)],
        times=[e.text for e in doc.ents if e.label_ in ("TIME", "DATE")],
        locations=[e.text for e in doc.ents if e.label_ in ("GPE", "LOC", "FAC")],
        positions=[e.text.lower() for e in doc.ents if e.label_ == "HOCKEY_POSITION"],
        actions=[
            e.text.lower()
            for e in doc.ents
            if e.label_ in ("ATTENDANCE_YES", "ATTENDANCE_NO")
        ],
    )

    intent, confidence = _classify_intent(raw_text, entities)

    # Safety guard (regex fast-path + optional Llama Guard)
    is_safe, safety_reason = await check_safety(raw_text)
    if not is_safe:
        log.warning(
            "preprocess.security_rejection",
            from_phone=context.get("from_phone"),
            reason=safety_reason,
        )
        raise SecurityError(safety_reason)

    log.info(
        "preprocess.done",
        intent=intent,
        confidence=confidence,
        entities=entities.model_dump(exclude_none=True),
        from_phone=context.get("from_phone"),
    )

    return StructuredInput(
        raw_text=raw_text,
        channel=context.get("channel", "sms"),
        from_phone=context.get("from_phone", ""),
        entities=entities,
        intent=intent,
        is_safe=True,
        confidence=confidence,
        metadata=context,
    )
