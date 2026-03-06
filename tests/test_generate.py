"""
Unit tests for Stage 3: Generation, Tool Calling & Agentic Loops.

All external dependencies are mocked:
  - anthropic.AsyncAnthropic (no API key required)
  - SQLAlchemy AsyncSession (no database required)
  - Tool implementations in app.stages.tools

Tests run without any running infrastructure.
"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.pipeline import EntityMap, Intent, StructuredInput


# ── Fixtures ──────────────────────────────────────────────────────────────────

CTX = {"team_id": 42, "channel": "sms", "from_phone": "+16135550101"}

ATTENDANCE_INPUT = StructuredInput(
    raw_text="yes I'll be there Tuesday",
    channel="sms",
    from_phone="+16135550101",
    entities=EntityMap(actions=["yes"]),
    intent=Intent.attendance_update,
    is_safe=True,
    confidence=0.9,
    metadata=CTX,
)

QUERY_INPUT = StructuredInput(
    raw_text="Who plays center?",
    channel="sms",
    from_phone="+16135550101",
    entities=EntityMap(positions=["center"]),
    intent=Intent.query,
    is_safe=True,
    confidence=0.8,
    metadata=CTX,
)

RAG_CHUNKS = [
    {"text": "Player: Alice. Position preferences: center.", "score": 0.92, "doc_type": "player"},
    {"text": "Player: Bob. Position preferences: wing, center.", "score": 0.85, "doc_type": "player"},
]


def _make_text_response(text: str, stop_reason: str = "end_turn") -> MagicMock:
    """Build a mock anthropic.types.Message with a text block."""
    block = SimpleNamespace(type="text", text=text)
    msg = MagicMock()
    msg.stop_reason = stop_reason
    msg.content = [block]
    msg.usage = SimpleNamespace(input_tokens=100, output_tokens=50)
    return msg


def _make_tool_use_response(tool_name: str, tool_input: dict, tool_id: str = "tu_abc") -> MagicMock:
    """Build a mock anthropic.types.Message with a tool_use block."""
    block = SimpleNamespace(
        type="tool_use",
        id=tool_id,
        name=tool_name,
        input=tool_input,
    )
    msg = MagicMock()
    msg.stop_reason = "tool_use"
    msg.content = [block]
    msg.usage = SimpleNamespace(input_tokens=120, output_tokens=40)
    return msg


# ── Prompt rendering tests ────────────────────────────────────────────────────

class TestPromptRendering:
    def test_attendance_prompt_includes_raw_text(self):
        """Attendance template renders raw_text into user message."""
        from app.stages.generation.prompts import render_prompt
        system, user = render_prompt(ATTENDANCE_INPUT, [], CTX)
        assert "yes I'll be there Tuesday" in user
        assert "team_id" in system.lower() or "leeg" in system.lower()

    def test_query_prompt_includes_rag_chunks(self):
        """General query template injects RAG chunk text into user message."""
        from app.stages.generation.prompts import render_prompt
        system, user = render_prompt(QUERY_INPUT, RAG_CHUNKS, CTX)
        assert "Alice" in user
        assert "Bob" in user

    def test_lineup_prompt_includes_criteria(self):
        """Lineup template uses criteria from context."""
        lineup_input = StructuredInput(
            raw_text="Set the lines for Tuesday",
            channel="sms",
            from_phone="+16135550101",
            intent=Intent.lineup_request,
            is_safe=True,
            confidence=0.9,
            metadata=CTX,
        )
        from app.stages.generation.prompts import render_prompt
        _, user = render_prompt(lineup_input, [], {**CTX, "criteria": "balance skill levels"})
        assert "balance skill levels" in user

    def test_all_intents_render_without_error(self):
        """Every intent has a registered template and renders cleanly."""
        from app.stages.generation.prompts import render_prompt
        for intent in Intent:
            si = StructuredInput(
                raw_text="test message",
                channel="sms",
                from_phone="+16135550101",
                intent=intent,
                is_safe=True,
                confidence=0.5,
                metadata=CTX,
            )
            system, user = render_prompt(si, [], CTX)
            assert isinstance(system, str) and len(system) > 0
            assert isinstance(user, str) and len(user) > 0


# ── generate_response / call_llm tests ───────────────────────────────────────

class TestGenerateResponse:
    def test_generate_response_calls_anthropic_client(self):
        """generate_response calls the Anthropic API with expected arguments."""
        mock_response = _make_text_response("Alice plays center.")

        async def run():
            with patch("app.stages.generation.generate._get_client") as mock_client_factory:
                mock_client = MagicMock()
                mock_client.messages.create = AsyncMock(return_value=mock_response)
                mock_client_factory.return_value = mock_client

                from app.stages.generation.generate import generate_response
                result = await generate_response(QUERY_INPUT, RAG_CHUNKS, CTX)

            assert result.stop_reason == "end_turn"
            create_call = mock_client.messages.create.call_args
            assert create_call.kwargs["model"].startswith("claude-haiku")
            assert "tools" in create_call.kwargs
            assert len(create_call.kwargs["tools"]) > 0

        asyncio.run(run())

    def test_extract_text_from_text_response(self):
        """extract_text returns concatenated text blocks."""
        from app.stages.generation.generate import extract_text
        response = _make_text_response("Hello world")
        assert extract_text(response) == "Hello world"

    def test_extract_text_empty_on_tool_use_only(self):
        """extract_text returns empty string when response has no text blocks."""
        from app.stages.generation.generate import extract_text
        response = _make_tool_use_response("get_roster", {"team_id": 42})
        assert extract_text(response) == ""

    def test_extract_tool_uses_from_tool_use_response(self):
        """extract_tool_uses returns all tool_use blocks."""
        from app.stages.generation.generate import extract_tool_uses
        response = _make_tool_use_response("update_attendance", {"game_id": 1, "player_id": 2, "status": "yes"})
        tools = extract_tool_uses(response)
        assert len(tools) == 1
        assert tools[0]["name"] == "update_attendance"
        assert tools[0]["input"]["status"] == "yes"


# ── Tool dispatch tests ───────────────────────────────────────────────────────

class TestToolDispatch:
    def test_dispatch_unknown_tool_raises(self):
        """dispatch_tool raises ValueError for unknown tool names."""
        async def run():
            mock_db = AsyncMock()
            from app.stages.generation.tools import dispatch_tool
            with pytest.raises(ValueError, match="Unknown tool"):
                await dispatch_tool("nonexistent_tool", {}, mock_db)
        asyncio.run(run())

    def test_dispatch_get_roster(self):
        """dispatch_tool routes get_roster to the correct implementation."""
        player = MagicMock()
        player.id = 1
        player.name = "Alice"
        player.team_id = 42
        player.position_prefs = ["center"]
        player.skill_notes = "Fast skater"
        player.sub_flag = False

        async def run():
            mock_db = AsyncMock()
            result_mock = MagicMock()
            result_mock.scalars.return_value.all.return_value = [player]
            mock_db.execute = AsyncMock(return_value=result_mock)

            from app.stages.generation.tools import dispatch_tool
            result = await dispatch_tool("get_roster", {"team_id": 42}, mock_db)

        asyncio.run(run())

    def test_dispatch_update_attendance(self):
        """dispatch_tool routes update_attendance and commits."""
        async def run():
            mock_db = AsyncMock()
            mock_db.execute = AsyncMock()
            mock_db.commit = AsyncMock()

            with patch("app.stages.generation.tools.pg_insert") as mock_insert:
                mock_stmt = MagicMock()
                mock_stmt.values.return_value.on_conflict_do_update.return_value = mock_stmt
                mock_insert.return_value = mock_stmt

                from app.stages.generation.tools import dispatch_tool
                result = await dispatch_tool(
                    "update_attendance",
                    {"game_id": 1, "player_id": 2, "status": "yes"},
                    mock_db,
                )

            assert result["ok"] is True
            mock_db.commit.assert_called_once()

        asyncio.run(run())

    def test_send_sms_skipped_when_twilio_not_configured(self):
        """send_sms returns ok=False gracefully when Twilio creds are absent."""
        async def run():
            mock_db = AsyncMock()
            # settings is lazily imported inside _send_sms, so patch at source
            with patch("app.config.settings") as mock_settings:
                mock_settings.twilio_account_sid = ""
                from app.stages.generation.tools import dispatch_tool
                result = await dispatch_tool(
                    "send_sms",
                    {"to_phone": "+16135550101", "message": "Hi"},
                    mock_db,
                )
            assert result["ok"] is False

        asyncio.run(run())


# ── Agent loop tests ──────────────────────────────────────────────────────────

class TestAgentLoop:
    def test_agent_terminates_on_end_turn(self):
        """Agent loop exits cleanly when Claude returns stop_reason='end_turn'."""
        mock_response = _make_text_response("Alice plays center.", stop_reason="end_turn")

        async def run():
            mock_db = AsyncMock()
            with patch("app.stages.generation.generate._get_client") as mock_client_factory:
                mock_client = MagicMock()
                mock_client.messages.create = AsyncMock(return_value=mock_response)
                mock_client_factory.return_value = mock_client

                from app.stages.generation.agent import run_agent
                result = await run_agent(QUERY_INPUT, RAG_CHUNKS, CTX, mock_db)

            assert result["stop_reason"] == "end_turn"
            assert result["iterations"] == 1
            assert "Alice" in result["answer"]
            assert result["tool_calls"] == []

        asyncio.run(run())

    def test_agent_executes_tool_and_continues(self):
        """Agent dispatches a tool call and makes a second LLM call with the result."""
        tool_response = _make_tool_use_response(
            "get_roster", {"team_id": 42}, tool_id="tu_roster"
        )
        final_response = _make_text_response("The roster has Alice and Bob.", stop_reason="end_turn")

        async def run():
            mock_db = AsyncMock()
            result_mock = MagicMock()
            result_mock.scalars.return_value.all.return_value = []
            mock_db.execute = AsyncMock(return_value=result_mock)

            call_count = {"n": 0}
            async def mock_create(**kwargs):
                call_count["n"] += 1
                return tool_response if call_count["n"] == 1 else final_response

            with patch("app.stages.generation.generate._get_client") as mock_client_factory:
                mock_client = MagicMock()
                mock_client.messages.create = AsyncMock(side_effect=mock_create)
                mock_client_factory.return_value = mock_client

                from app.stages.generation.agent import run_agent
                result = await run_agent(ATTENDANCE_INPUT, [], CTX, mock_db)

            assert result["iterations"] == 2
            assert len(result["tool_calls"]) == 1
            assert result["tool_calls"][0]["name"] == "get_roster"

        asyncio.run(run())

    def test_agent_stops_at_max_iterations(self):
        """Agent loop terminates after MAX_ITERATIONS even if Claude keeps requesting tools."""
        tool_response = _make_tool_use_response("get_roster", {"team_id": 42})

        async def run():
            mock_db = AsyncMock()
            result_mock = MagicMock()
            result_mock.scalars.return_value.all.return_value = []
            mock_db.execute = AsyncMock(return_value=result_mock)

            with patch("app.stages.generation.generate._get_client") as mock_client_factory:
                mock_client = MagicMock()
                # Always return tool_use — never end_turn
                mock_client.messages.create = AsyncMock(return_value=tool_response)
                mock_client_factory.return_value = mock_client

                from app.stages.generation.agent import MAX_ITERATIONS, run_agent
                result = await run_agent(ATTENDANCE_INPUT, [], CTX, mock_db)

            assert result["iterations"] == MAX_ITERATIONS
            assert result["stop_reason"] == "tool_use"  # last stop_reason before forced exit

        asyncio.run(run())
