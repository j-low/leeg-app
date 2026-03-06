"""
Stage 4: Post-processing orchestrator.

Receives the raw agent loop output (Stage 3) and transforms it into the
final, delivery-ready PostprocessedResponse via four sequential steps:

  1. Validate   — extract and validate the answer string; fall back to a
                  safe message if the answer is missing or empty.
  2. Redact PII — run Presidio + roster-aware name suppression.
  3. Format     — apply channel-specific rules (SMS length, encoding;
                  dashboard structured payload).
  4. Audit log  — emit a structlog entry for compliance and observability.

Guarantees:
  - Never raises. Any unhandled exception returns a safe fallback response.
  - Never logs the full text_for_user (only its length).
  - Always returns PostprocessedResponse regardless of what Stage 3 produced.
"""
import logging

import structlog

from app.schemas.pipeline import PostprocessedResponse, StructuredInput
from app.stages.postprocess.formatter import format_for_dashboard, format_for_sms
from app.stages.postprocess.pii import redact_pii

log = structlog.get_logger(__name__)

_FALLBACK_TEXT = "Sorry, something went wrong. Please try again."


async def postprocess(
    raw_output: dict,
    context: dict,
    structured_input: StructuredInput,
) -> PostprocessedResponse:
    """Stage 4 entry point: validate → redact → format → audit log.

    Args:
        raw_output:       Dict from run_agent():
                          {answer, tool_calls, iterations, stop_reason}.
        context:          Pipeline context dict: {team_id, channel, from_phone, ...}.
                          Optional key: "known_player_names" (list[str]) — injected by
                          Phase 9 pipeline orchestrator for roster-aware PII redaction.
        structured_input: Stage 1 output — used for channel, intent, and audit logging.

    Returns:
        PostprocessedResponse — always. Never raises.
    """
    channel = context.get("channel", structured_input.channel or "sms")

    try:
        mutations: list[str] = []

        # ── Step 1: Validate answer ───────────────────────────────────────────
        answer = raw_output.get("answer", "")
        if not answer or not answer.strip():
            answer = _FALLBACK_TEXT
            mutations.append("fallback:empty_answer")
            log.warning(
                "postprocess.empty_answer",
                stop_reason=raw_output.get("stop_reason"),
                channel=channel,
            )

        # ── Step 2: PII redaction ─────────────────────────────────────────────
        extra_names: list[str] = context.get("known_player_names", [])
        redacted, pii_found = await redact_pii(answer, extra_names=extra_names)
        if pii_found:
            mutations.append("pii_redacted")

        # ── Step 3: Channel-specific formatting ───────────────────────────────
        dashboard_payload: dict | None = None
        was_truncated = False

        if channel == "dashboard":
            final_text, dashboard_payload = format_for_dashboard(redacted, raw_output)
        else:
            # Default: SMS
            final_text, was_truncated = format_for_sms(redacted)
            if was_truncated:
                mutations.append("truncated")

        # ── Step 4: Audit log ─────────────────────────────────────────────────
        log.info(
            "postprocess.done",
            channel=channel,
            intent=str(structured_input.intent),
            team_id=context.get("team_id"),
            pii_detected=pii_found,
            was_truncated=was_truncated,
            mutations=mutations,
            output_len=len(final_text),
            tool_call_count=len(raw_output.get("tool_calls", [])),
            iterations=raw_output.get("iterations", 0),
            stop_reason=raw_output.get("stop_reason", ""),
        )

        return PostprocessedResponse(
            text_for_user=final_text,
            channel=channel,
            mutations=mutations,
            pii_detected=pii_found,
            was_truncated=was_truncated,
            tool_calls=raw_output.get("tool_calls", []),
            iterations=raw_output.get("iterations", 0),
            stop_reason=raw_output.get("stop_reason", ""),
            dashboard_payload=dashboard_payload,
        )

    except Exception as exc:
        log.error(
            "postprocess.failed",
            error=str(exc),
            channel=channel,
            stop_reason=raw_output.get("stop_reason", "unknown"),
        )
        return PostprocessedResponse(
            text_for_user=_FALLBACK_TEXT,
            channel=channel,
            mutations=["fallback:exception"],
            stop_reason=raw_output.get("stop_reason", "unknown"),
        )
