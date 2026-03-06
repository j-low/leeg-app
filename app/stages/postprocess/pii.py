"""
Stage 4: PII detection and redaction.

Uses Microsoft Presidio for standard PII (PHONE_NUMBER, EMAIL_ADDRESS, PERSON)
plus a custom hockey-context recognizer for patterns like captain note leakage.

Design notes:
  - Analyzer and anonymizer are module-level singletons (expensive to initialize;
    same pattern as _build_nlp() in preprocess.py).
  - Presidio's analyze() is synchronous — called via asyncio.to_thread() to
    avoid blocking the FastAPI event loop.
  - redact_pii() never raises: any Presidio failure degrades gracefully (fail open).
  - extra_names provides roster-aware suppression of player names that
    standard NER might miss (short informal names like "Gretz", "Bobs").
    Applied as a simple str.replace pass — no regex, avoids false positives.
"""
import asyncio
import logging
import re

from presidio_analyzer import AnalyzerEngine, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine

log = logging.getLogger(__name__)

# ── PII entity types to scan for ─────────────────────────────────────────────
_ENTITIES = ["PHONE_NUMBER", "EMAIL_ADDRESS", "PERSON"]


# ── Custom hockey-context recognizer ─────────────────────────────────────────

class _HockeyCaptainNoteRecognizer(PatternRecognizer):
    """Catch leaked captain notes patterns in LLM output.

    These patterns are defense-in-depth: the system prompt already instructs
    Claude never to reveal captain_notes, but this recognizer provides a
    backstop in case the instruction is not followed.

    Matches phrases like:
      - "captain note: ..."
      - "note to captain: ..."
      - "[captain only]"
    """

    PATTERNS = [
        r"(?i)captain\s+note\s*:",
        r"(?i)note\s+to\s+captain\s*:",
        r"(?i)\[captain\s+only\]",
        r"(?i)captain['']?s?\s+comment\s*:",
    ]

    def __init__(self) -> None:
        from presidio_analyzer import Pattern
        patterns = [
            Pattern(name=f"captain_note_pattern_{i}", regex=p, score=0.9)
            for i, p in enumerate(self.PATTERNS)
        ]
        super().__init__(
            supported_entity="CAPTAIN_NOTE",
            patterns=patterns,
        )


# ── Module-level singletons ───────────────────────────────────────────────────

def _build_analyzer() -> AnalyzerEngine:
    """Build the Presidio AnalyzerEngine with custom recognizers.

    Uses the already-installed spacy en_core_web_sm model (no extra download).
    """
    try:
        provider = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
        })
        nlp_engine = provider.create_engine()
        analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
        analyzer.registry.add_recognizer(_HockeyCaptainNoteRecognizer())
        log.debug("pii._build_analyzer complete")
        return analyzer
    except Exception as exc:
        log.warning("pii._build_analyzer failed — PII detection disabled: %s", exc)
        return None  # type: ignore[return-value]


_analyzer: AnalyzerEngine | None = _build_analyzer()
_anonymizer: AnonymizerEngine = AnonymizerEngine()


# ── Public API ────────────────────────────────────────────────────────────────

async def redact_pii(
    text: str,
    extra_names: list[str] | None = None,
) -> tuple[str, bool]:
    """Detect and redact PII from text.

    Args:
        text:        The text to scan. Typically the LLM's answer string.
        extra_names: Optional list of player names from the team roster.
                     Names present in this list are replaced with <PERSON>
                     via a simple case-insensitive str.replace pass, catching
                     informal names that spaCy NER might miss.

    Returns:
        (redacted_text, pii_was_found)
        - redacted_text: text with PII replaced by <ENTITY_TYPE> placeholders.
        - pii_was_found: True if any PII was detected and replaced.

    Never raises. On any Presidio error, returns (original_text, False).
    """
    if not text:
        return text, False

    if _analyzer is None:
        log.warning("pii.redact_pii skipped — analyzer not initialized")
        return text, False

    try:
        # Presidio analyze() is synchronous — run in thread pool
        results = await asyncio.to_thread(
            _analyzer.analyze,
            text=text,
            language="en",
            entities=_ENTITIES + ["CAPTAIN_NOTE"],
        )

        pii_found = len(results) > 0

        if pii_found:
            anonymized = await asyncio.to_thread(
                _anonymizer.anonymize,
                text=text,
                analyzer_results=results,
            )
            redacted = anonymized.text
        else:
            redacted = text

        # Roster-aware name suppression (extra_names from context)
        if extra_names:
            redacted, name_found = _suppress_names(redacted, extra_names)
            if name_found:
                pii_found = True

        log.debug("pii.redact_pii pii_found=%s char_delta=%d", pii_found, len(text) - len(redacted))
        return redacted, pii_found

    except Exception as exc:
        log.warning("pii.redact_pii error — returning original text: %s", exc)
        return text, False


def _suppress_names(text: str, names: list[str]) -> tuple[str, bool]:
    """Replace occurrences of player names with <PERSON>.

    Uses word-boundary matching to avoid replacing substrings
    (e.g. "Bob" should not match inside "Bobby").

    Returns:
        (modified_text, any_replaced)
    """
    found = False
    for name in names:
        if not name or len(name) < 2:
            continue
        pattern = re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)
        if pattern.search(text):
            text = pattern.sub("<PERSON>", text)
            found = True
    return text, found
