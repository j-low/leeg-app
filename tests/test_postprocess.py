"""
Unit tests for Stage 4: Post-Processing.

All Presidio calls are mocked — no running infrastructure or spaCy model needed.

Test classes:
  - TestPiiRedaction  (5 cases) — redact_pii() with mocked AnalyzerEngine
  - TestFormatter     (4 cases) — format_for_sms(), format_for_dashboard(), encoding
  - TestPostprocess   (6 cases) — postprocess() orchestrator end-to-end
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.pipeline import EntityMap, Intent, StructuredInput


# ── Shared fixtures ────────────────────────────────────────────────────────────

CTX = {"team_id": 7, "channel": "sms", "from_phone": "+16135550101"}

STRUCTURED_INPUT = StructuredInput(
    raw_text="when is the next game?",
    channel="sms",
    from_phone="+16135550101",
    entities=EntityMap(),
    intent=Intent.schedule_query,
    is_safe=True,
    confidence=0.88,
    metadata=CTX,
)

RAW_OUTPUT_OK = {
    "answer": "Your next game is Tuesday at 9 PM.",
    "tool_calls": [],
    "iterations": 1,
    "stop_reason": "end_turn",
}


# ── TestPiiRedaction ───────────────────────────────────────────────────────────

class TestPiiRedaction:
    """Tests for app.stages.postprocess.pii.redact_pii()."""

    @pytest.mark.asyncio
    async def test_phone_number_redacted(self):
        """Phone number in text → replaced with <PHONE_NUMBER>, pii_found=True."""
        from presidio_analyzer import RecognizerResult

        fake_result = RecognizerResult(
            entity_type="PHONE_NUMBER", start=14, end=27, score=0.9
        )
        fake_anonymized = MagicMock()
        fake_anonymized.text = "Call us at <PHONE_NUMBER> anytime."

        with (
            patch("app.stages.postprocess.pii._analyzer") as mock_analyzer,
            patch("app.stages.postprocess.pii._anonymizer") as mock_anonymizer,
        ):
            mock_analyzer.analyze = MagicMock(return_value=[fake_result])
            mock_anonymizer.anonymize = MagicMock(return_value=fake_anonymized)

            from app.stages.postprocess.pii import redact_pii
            redacted, pii_found = await redact_pii("Call us at 555-867-5309 anytime.")

        assert pii_found is True
        assert "<PHONE_NUMBER>" in redacted

    @pytest.mark.asyncio
    async def test_email_redacted(self):
        """Email address → replaced, pii_found=True."""
        from presidio_analyzer import RecognizerResult

        fake_result = RecognizerResult(
            entity_type="EMAIL_ADDRESS", start=9, end=28, score=0.95
        )
        fake_anonymized = MagicMock()
        fake_anonymized.text = "Contact <EMAIL_ADDRESS> for details."

        with (
            patch("app.stages.postprocess.pii._analyzer") as mock_analyzer,
            patch("app.stages.postprocess.pii._anonymizer") as mock_anonymizer,
        ):
            mock_analyzer.analyze = MagicMock(return_value=[fake_result])
            mock_anonymizer.anonymize = MagicMock(return_value=fake_anonymized)

            from app.stages.postprocess.pii import redact_pii
            redacted, pii_found = await redact_pii("Contact coach@leeg.app for details.")

        assert pii_found is True
        assert "<EMAIL_ADDRESS>" in redacted

    @pytest.mark.asyncio
    async def test_clean_text_passes_through(self):
        """Text with no PII → returned unchanged, pii_found=False."""
        with (
            patch("app.stages.postprocess.pii._analyzer") as mock_analyzer,
            patch("app.stages.postprocess.pii._anonymizer"),
        ):
            mock_analyzer.analyze = MagicMock(return_value=[])

            from app.stages.postprocess.pii import redact_pii
            original = "Your next game is Tuesday at 9 PM."
            redacted, pii_found = await redact_pii(original)

        assert pii_found is False
        assert redacted == original

    @pytest.mark.asyncio
    async def test_extra_names_suppressed(self):
        """extra_names=['Alice'] → 'Alice' replaced with <PERSON> in output."""
        with (
            patch("app.stages.postprocess.pii._analyzer") as mock_analyzer,
            patch("app.stages.postprocess.pii._anonymizer"),
        ):
            mock_analyzer.analyze = MagicMock(return_value=[])

            from app.stages.postprocess.pii import redact_pii
            redacted, pii_found = await redact_pii(
                "Alice will play center on Tuesday.",
                extra_names=["Alice"],
            )

        assert pii_found is True
        assert "Alice" not in redacted
        assert "<PERSON>" in redacted

    @pytest.mark.asyncio
    async def test_presidio_exception_fails_open(self):
        """Presidio raises → returns (original_text, False), never raises."""
        with patch("app.stages.postprocess.pii._analyzer") as mock_analyzer:
            mock_analyzer.analyze = MagicMock(side_effect=RuntimeError("spacy crash"))

            from app.stages.postprocess.pii import redact_pii
            original = "Some text with a name."
            redacted, pii_found = await redact_pii(original)

        assert pii_found is False
        assert redacted == original


# ── TestFormatter ──────────────────────────────────────────────────────────────

class TestFormatter:
    """Tests for app.stages.postprocess.formatter functions."""

    def test_short_sms_not_truncated(self):
        """100-char text → returned as-is, was_truncated=False."""
        from app.stages.postprocess.formatter import format_for_sms

        text = "A" * 100
        result, was_truncated = format_for_sms(text)

        assert was_truncated is False
        assert result == text

    def test_over_hard_limit_truncated(self):
        """1700-char text → truncated to ≤ 1600, was_truncated=True, ends with '...'."""
        from app.stages.postprocess.formatter import SMS_HARD_LIMIT, format_for_sms

        text = "word " * 340  # 1700 chars
        result, was_truncated = format_for_sms(text)

        assert was_truncated is True
        assert len(result) <= SMS_HARD_LIMIT
        assert result.endswith("...")

    def test_smart_quotes_normalized(self):
        """Curly quotes and em-dashes → ASCII equivalents."""
        from app.stages.postprocess.formatter import format_for_sms

        text = "\u201cHello\u201d \u2013 it\u2019s fine\u2026"
        result, _ = format_for_sms(text)

        assert "\u201c" not in result
        assert "\u201d" not in result
        assert "\u2013" not in result
        assert "\u2019" not in result
        assert "\u2026" not in result
        assert '"Hello"' in result
        assert "it's fine..." in result

    def test_dashboard_payload_structure(self):
        """format_for_dashboard returns text + payload with expected keys."""
        from app.stages.postprocess.formatter import format_for_dashboard

        raw = {
            "answer": "Lineup set.",
            "tool_calls": [{"name": "suggest_lineup", "input": {}, "result": "ok"}],
            "iterations": 2,
            "stop_reason": "end_turn",
        }
        text, payload = format_for_dashboard("Lineup set.", raw)

        assert text == "Lineup set."
        assert payload["answer"] == "Lineup set."
        assert payload["tool_calls"] == raw["tool_calls"]
        assert payload["iterations"] == 2
        assert payload["stop_reason"] == "end_turn"


# ── TestPostprocess ────────────────────────────────────────────────────────────

class TestPostprocess:
    """Tests for app.stages.postprocess.postprocess.postprocess()."""

    @pytest.mark.asyncio
    async def test_happy_path_sms(self):
        """Clean answer on SMS channel → correct text_for_user, channel='sms'."""
        with (
            patch("app.stages.postprocess.postprocess.redact_pii", new_callable=AsyncMock) as mock_pii,
            patch("app.stages.postprocess.postprocess.format_for_sms") as mock_fmt,
        ):
            mock_pii.return_value = ("Your next game is Tuesday at 9 PM.", False)
            mock_fmt.return_value = ("Your next game is Tuesday at 9 PM.", False)

            from app.stages.postprocess.postprocess import postprocess
            result = await postprocess(RAW_OUTPUT_OK, CTX, STRUCTURED_INPUT)

        assert result.text_for_user == "Your next game is Tuesday at 9 PM."
        assert result.channel == "sms"
        assert result.pii_detected is False
        assert result.was_truncated is False
        assert result.stop_reason == "end_turn"
        assert result.iterations == 1

    @pytest.mark.asyncio
    async def test_happy_path_dashboard(self):
        """Dashboard channel → dashboard_payload populated."""
        ctx_dash = {**CTX, "channel": "dashboard"}
        raw = {**RAW_OUTPUT_OK, "tool_calls": [{"name": "get_roster", "input": {}, "result": "..."}]}

        with (
            patch("app.stages.postprocess.postprocess.redact_pii", new_callable=AsyncMock) as mock_pii,
            patch("app.stages.postprocess.postprocess.format_for_dashboard") as mock_fmt,
        ):
            mock_pii.return_value = ("Your next game is Tuesday at 9 PM.", False)
            mock_fmt.return_value = (
                "Your next game is Tuesday at 9 PM.",
                {"answer": "Your next game is Tuesday at 9 PM.", "tool_calls": raw["tool_calls"], "iterations": 1, "stop_reason": "end_turn"},
            )

            from app.stages.postprocess.postprocess import postprocess
            result = await postprocess(raw, ctx_dash, STRUCTURED_INPUT)

        assert result.channel == "dashboard"
        assert result.dashboard_payload is not None
        assert "tool_calls" in result.dashboard_payload

    @pytest.mark.asyncio
    async def test_pii_detected_in_answer(self):
        """PII in answer → pii_detected=True, 'pii_redacted' in mutations."""
        with (
            patch("app.stages.postprocess.postprocess.redact_pii", new_callable=AsyncMock) as mock_pii,
            patch("app.stages.postprocess.postprocess.format_for_sms") as mock_fmt,
        ):
            mock_pii.return_value = ("Contact <EMAIL_ADDRESS> for info.", True)
            mock_fmt.return_value = ("Contact <EMAIL_ADDRESS> for info.", False)

            from app.stages.postprocess.postprocess import postprocess
            result = await postprocess(RAW_OUTPUT_OK, CTX, STRUCTURED_INPUT)

        assert result.pii_detected is True
        assert "pii_redacted" in result.mutations

    @pytest.mark.asyncio
    async def test_empty_answer_uses_fallback(self):
        """Missing/empty answer → fallback text, 'fallback:empty_answer' in mutations."""
        raw_empty = {**RAW_OUTPUT_OK, "answer": ""}

        with (
            patch("app.stages.postprocess.postprocess.redact_pii", new_callable=AsyncMock) as mock_pii,
            patch("app.stages.postprocess.postprocess.format_for_sms") as mock_fmt,
        ):
            mock_pii.return_value = ("Sorry, something went wrong. Please try again.", False)
            mock_fmt.return_value = ("Sorry, something went wrong. Please try again.", False)

            from app.stages.postprocess.postprocess import postprocess
            result = await postprocess(raw_empty, CTX, STRUCTURED_INPUT)

        assert "fallback:empty_answer" in result.mutations
        assert "Sorry" in result.text_for_user

    @pytest.mark.asyncio
    async def test_exception_returns_fallback_no_raise(self):
        """Unhandled exception inside postprocess → safe fallback returned, never raises."""
        with patch("app.stages.postprocess.postprocess.redact_pii", new_callable=AsyncMock) as mock_pii:
            mock_pii.side_effect = RuntimeError("unexpected crash")

            from app.stages.postprocess.postprocess import postprocess
            result = await postprocess(RAW_OUTPUT_OK, CTX, STRUCTURED_INPUT)

        assert result.text_for_user == "Sorry, something went wrong. Please try again."
        assert "fallback:exception" in result.mutations

    @pytest.mark.asyncio
    async def test_audit_log_emitted(self):
        """structlog audit log emitted with expected keys."""
        with (
            patch("app.stages.postprocess.postprocess.redact_pii", new_callable=AsyncMock) as mock_pii,
            patch("app.stages.postprocess.postprocess.format_for_sms") as mock_fmt,
            patch("app.stages.postprocess.postprocess.log") as mock_log,
        ):
            mock_pii.return_value = ("Your next game is Tuesday at 9 PM.", False)
            mock_fmt.return_value = ("Your next game is Tuesday at 9 PM.", False)

            from app.stages.postprocess.postprocess import postprocess
            await postprocess(RAW_OUTPUT_OK, CTX, STRUCTURED_INPUT)

        mock_log.info.assert_called_once()
        call_kwargs = mock_log.info.call_args
        # structlog info("event", key=val) — check the event name
        assert call_kwargs.args[0] == "postprocess.done"
        # Verify key audit fields are present
        logged = call_kwargs.kwargs
        assert "channel" in logged
        assert "pii_detected" in logged
        assert "mutations" in logged
        assert "output_len" in logged
        # Never log the full text — only length
        assert "text_for_user" not in logged
