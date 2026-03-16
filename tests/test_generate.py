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

    def test_agent_treats_max_tokens_as_final_answer(self):
        """stop_reason='max_tokens' routes to END (same as end_turn), returning accumulated text."""
        mock_response = _make_text_response("Partial answer cut off here", stop_reason="max_tokens")

        async def run():
            mock_db = AsyncMock()
            with patch("app.stages.generation.generate._get_client") as mock_client_factory:
                mock_client = MagicMock()
                mock_client.messages.create = AsyncMock(return_value=mock_response)
                mock_client_factory.return_value = mock_client

                from app.stages.generation.agent import run_agent
                result = await run_agent(QUERY_INPUT, RAG_CHUNKS, CTX, mock_db)

            assert result["stop_reason"] == "max_tokens"
            assert result["iterations"] == 1
            assert "Partial answer" in result["answer"]
            assert result["tool_calls"] == []

        asyncio.run(run())

    def test_agent_continues_after_tool_dispatch_error(self):
        """Tool exception is caught, recorded with 'error' key, and agent continues to next LLM call."""
        tool_response = _make_tool_use_response("get_roster", {"team_id": 42}, tool_id="tu_err")
        final_response = _make_text_response("Could not retrieve roster.", stop_reason="end_turn")

        async def run():
            mock_db = AsyncMock()

            call_count = {"n": 0}
            async def mock_create(**kwargs):
                call_count["n"] += 1
                return tool_response if call_count["n"] == 1 else final_response

            with (
                patch("app.stages.generation.generate._get_client") as mock_client_factory,
                patch("app.stages.generation.agent.dispatch_tool", new_callable=AsyncMock) as mock_dispatch,
            ):
                mock_client = MagicMock()
                mock_client.messages.create = AsyncMock(side_effect=mock_create)
                mock_client_factory.return_value = mock_client
                mock_dispatch.side_effect = RuntimeError("DB connection lost")

                from app.stages.generation.agent import run_agent
                result = await run_agent(QUERY_INPUT, RAG_CHUNKS, CTX, mock_db)

            # Agent must not raise — it continues and produces an answer
            assert result["stop_reason"] == "end_turn"
            assert result["iterations"] == 2
            # Tool call log records the error, not a result
            assert len(result["tool_calls"]) == 1
            assert "error" in result["tool_calls"][0]
            assert "result" not in result["tool_calls"][0]

        asyncio.run(run())

    def test_agent_dispatches_multiple_tools_in_one_turn(self):
        """All tool_use blocks in a single response are dispatched before the next LLM call."""
        from types import SimpleNamespace

        # Response with two tool_use blocks
        block1 = SimpleNamespace(type="tool_use", id="tu_1", name="get_roster",   input={"team_id": 42})
        block2 = SimpleNamespace(type="tool_use", id="tu_2", name="get_attendance", input={"game_id": 1})
        multi_tool_msg = MagicMock()
        multi_tool_msg.stop_reason = "tool_use"
        multi_tool_msg.content = [block1, block2]
        multi_tool_msg.usage = SimpleNamespace(input_tokens=130, output_tokens=45)

        final_response = _make_text_response("Here is the info.", stop_reason="end_turn")

        async def run():
            mock_db = AsyncMock()

            call_count = {"n": 0}
            async def mock_create(**kwargs):
                call_count["n"] += 1
                return multi_tool_msg if call_count["n"] == 1 else final_response

            with (
                patch("app.stages.generation.generate._get_client") as mock_client_factory,
                patch("app.stages.generation.agent.dispatch_tool", new_callable=AsyncMock) as mock_dispatch,
            ):
                mock_client = MagicMock()
                mock_client.messages.create = AsyncMock(side_effect=mock_create)
                mock_client_factory.return_value = mock_client
                mock_dispatch.return_value = {"ok": True}

                from app.stages.generation.agent import run_agent
                result = await run_agent(QUERY_INPUT, RAG_CHUNKS, CTX, mock_db)

            # Both tools dispatched in a single execute_tools pass
            assert mock_dispatch.call_count == 2
            dispatched_names = {c.args[0] for c in mock_dispatch.call_args_list}
            assert dispatched_names == {"get_roster", "get_attendance"}
            assert len(result["tool_calls"]) == 2

        asyncio.run(run())

    def test_agent_tool_results_fed_back_as_user_message(self):
        """Tool results are appended as a 'user' role message with tool_result content blocks (Anthropic protocol)."""
        tool_response = _make_tool_use_response("get_roster", {"team_id": 42}, tool_id="tu_check")
        final_response = _make_text_response("Roster retrieved.", stop_reason="end_turn")

        captured_messages = {}

        async def run():
            mock_db = AsyncMock()

            call_count = {"n": 0}
            async def mock_create(**kwargs):
                call_count["n"] += 1
                if call_count["n"] == 2:
                    # Capture messages on the second (post-tool) call
                    captured_messages["msgs"] = kwargs.get("messages", [])
                return tool_response if call_count["n"] == 1 else final_response

            with (
                patch("app.stages.generation.generate._get_client") as mock_client_factory,
                patch("app.stages.generation.agent.dispatch_tool", new_callable=AsyncMock) as mock_dispatch,
            ):
                mock_client = MagicMock()
                mock_client.messages.create = AsyncMock(side_effect=mock_create)
                mock_client_factory.return_value = mock_client
                mock_dispatch.return_value = {"players": []}

                from app.stages.generation.agent import run_agent
                await run_agent(QUERY_INPUT, RAG_CHUNKS, CTX, mock_db)

            # The last message fed to the second LLM call must be the tool result user turn
            msgs = captured_messages["msgs"]
            tool_result_turn = msgs[-1]
            assert tool_result_turn["role"] == "user"
            assert isinstance(tool_result_turn["content"], list)
            assert tool_result_turn["content"][0]["type"] == "tool_result"
            assert tool_result_turn["content"][0]["tool_use_id"] == "tu_check"

        asyncio.run(run())


# ── TestStreamAgent ───────────────────────────────────────────────────────────

class _MockStream:
    """Simulates the anthropic streaming context manager."""

    def __init__(self, texts: list[str], final_msg):
        self._texts = texts
        self._final_msg = final_msg

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    @property
    def text_stream(self):
        async def _gen():
            for t in self._texts:
                yield t
        return _gen()

    async def get_final_message(self):
        return self._final_msg


def _make_stream_text_msg(texts: list[str]) -> tuple[_MockStream, MagicMock]:
    """Build a _MockStream whose final message is an end_turn text response."""
    final_msg = _make_text_response(" ".join(texts), stop_reason="end_turn")
    # Remove text blocks from content so tool extraction finds nothing
    final_msg.content = []
    return _MockStream(texts, final_msg), final_msg


def _make_stream_tool_msg(tool_name: str, tool_input: dict, tool_id: str = "tu_s1") -> tuple[_MockStream, MagicMock]:
    """Build a _MockStream whose final message is a tool_use stop."""
    block = SimpleNamespace(type="tool_use", id=tool_id, name=tool_name, input=tool_input)
    final_msg = MagicMock()
    final_msg.stop_reason = "tool_use"
    final_msg.content = [block]
    final_msg.usage = SimpleNamespace(input_tokens=80, output_tokens=30)
    return _MockStream([], final_msg), final_msg


async def _collect_stream(gen):
    events = []
    async for e in gen:
        events.append(e)
    return events


@pytest.mark.unit
class TestStreamAgent:
    """Unit tests for stream_agent() — the streaming variant of the ReAct loop."""

    @pytest.mark.asyncio
    async def test_stream_agent_yields_answer_token_events(self):
        """Text tokens emitted during streaming appear as answer_token events."""
        mock_client = MagicMock()
        stream_ctx, _ = _make_stream_text_msg(["Hello", " world"])
        mock_client.messages.stream.return_value = stream_ctx

        mock_db = AsyncMock()
        with (
            patch("app.stages.generation.generate._get_client", return_value=mock_client),
            patch("app.stages.generation.prompts.render_prompt", return_value=("system", "user")),
        ):
            from app.stages.generation.agent import stream_agent
            events = await _collect_stream(stream_agent(QUERY_INPUT, RAG_CHUNKS, CTX, mock_db))

        token_events = [e for e in events if e["type"] == "answer_token"]
        assert len(token_events) == 2
        texts = [e["text"] for e in token_events]
        assert "Hello" in texts
        assert " world" in texts

    @pytest.mark.asyncio
    async def test_stream_agent_yields_tool_start_and_tool_result_events(self):
        """tool_start event emitted before dispatch; tool_result after."""
        mock_client = MagicMock()
        tool_stream, _ = _make_stream_tool_msg("get_roster", {"team_id": 7})
        text_stream, _ = _make_stream_text_msg(["Done."])

        call_count = 0

        def _stream_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            return tool_stream if call_count == 1 else text_stream

        mock_client.messages.stream.side_effect = _stream_side_effect
        mock_db = AsyncMock()

        with (
            patch("app.stages.generation.agent._get_client", return_value=mock_client),
            patch("app.stages.generation.agent.render_prompt", return_value=("sys", "usr")),
            patch("app.stages.generation.agent.dispatch_tool", new=AsyncMock(return_value={"players": []})),
        ):
            from app.stages.generation.agent import stream_agent
            events = await _collect_stream(stream_agent(ATTENDANCE_INPUT, RAG_CHUNKS, CTX, mock_db))

        types = [e["type"] for e in events]
        assert "tool_start" in types
        assert "tool_result" in types

        tool_start = next(e for e in events if e["type"] == "tool_start")
        assert tool_start["name"] == "get_roster"

    @pytest.mark.asyncio
    async def test_stream_agent_yields_no_done_event(self):
        """stream_agent does NOT yield a 'done' event — caller handles that."""
        mock_client = MagicMock()
        stream_ctx, _ = _make_stream_text_msg(["answer"])
        mock_client.messages.stream.return_value = stream_ctx
        mock_db = AsyncMock()

        with (
            patch("app.stages.generation.generate._get_client", return_value=mock_client),
            patch("app.stages.generation.prompts.render_prompt", return_value=("s", "u")),
        ):
            from app.stages.generation.agent import stream_agent
            events = await _collect_stream(stream_agent(QUERY_INPUT, [], CTX, mock_db))

        done_events = [e for e in events if e["type"] == "done"]
        assert len(done_events) == 0

    @pytest.mark.asyncio
    async def test_stream_agent_respects_max_iterations(self):
        """Loop terminates after MAX_ITERATIONS even with continuous tool_use stops."""
        from app.stages.generation.agent import MAX_ITERATIONS

        mock_client = MagicMock()
        # Every LLM call returns a tool_use stop (infinite loop scenario)
        tool_stream_factory = lambda: _make_stream_tool_msg("get_roster", {"team_id": 1}, "tu_x")[0]  # noqa: E731
        mock_client.messages.stream.side_effect = lambda **kw: tool_stream_factory()
        mock_db = AsyncMock()

        with (
            patch("app.stages.generation.generate._get_client", return_value=mock_client),
            patch("app.stages.generation.prompts.render_prompt", return_value=("s", "u")),
            patch("app.stages.generation.agent.dispatch_tool", new=AsyncMock(return_value={})),
        ):
            from app.stages.generation.agent import stream_agent
            events = await _collect_stream(stream_agent(QUERY_INPUT, [], CTX, mock_db))

        # Should have terminated — not hung forever
        tool_start_events = [e for e in events if e["type"] == "tool_start"]
        assert len(tool_start_events) <= MAX_ITERATIONS

    @pytest.mark.asyncio
    async def test_stream_agent_timeout_yields_fallback_token(self):
        """asyncio.TimeoutError during streaming yields a fallback answer_token."""
        mock_client = MagicMock()

        # Stream context that raises TimeoutError on entry
        class _TimingOutStream:
            async def __aenter__(self):
                raise asyncio.TimeoutError()

            async def __aexit__(self, *args):
                pass

        mock_client.messages.stream.return_value = _TimingOutStream()
        mock_db = AsyncMock()

        with (
            patch("app.stages.generation.generate._get_client", return_value=mock_client),
            patch("app.stages.generation.prompts.render_prompt", return_value=("s", "u")),
        ):
            from app.stages.generation.agent import stream_agent
            events = await _collect_stream(stream_agent(QUERY_INPUT, [], CTX, mock_db))

        token_texts = [e["text"] for e in events if e["type"] == "answer_token"]
        assert any("too long" in t for t in token_texts)

    @pytest.mark.asyncio
    async def test_stream_agent_tool_error_yields_error_result(self):
        """Tool dispatch failure emits a tool_result with error payload."""
        mock_client = MagicMock()
        tool_stream, _ = _make_stream_tool_msg("get_roster", {"team_id": 1})
        text_stream, _ = _make_stream_text_msg(["ok"])
        call_n = {"n": 0}

        def _side(**kw):
            call_n["n"] += 1
            return tool_stream if call_n["n"] == 1 else text_stream

        mock_client.messages.stream.side_effect = _side
        mock_db = AsyncMock()

        with (
            patch("app.stages.generation.generate._get_client", return_value=mock_client),
            patch("app.stages.generation.prompts.render_prompt", return_value=("s", "u")),
            patch("app.stages.generation.agent.dispatch_tool", new=AsyncMock(side_effect=RuntimeError("DB down"))),
        ):
            from app.stages.generation.agent import stream_agent
            events = await _collect_stream(stream_agent(ATTENDANCE_INPUT, [], CTX, mock_db))

        tool_result_events = [e for e in events if e["type"] == "tool_result"]
        assert len(tool_result_events) >= 1
        # The result should carry the error info
        assert "error" in tool_result_events[0]["result"]

    @pytest.mark.asyncio
    async def test_stream_agent_re_raises_non_timeout_exception(self):
        """Non-TimeoutError exceptions propagate so pipeline can emit error event."""
        mock_client = MagicMock()

        class _BoomStream:
            async def __aenter__(self):
                raise RuntimeError("network failure")

            async def __aexit__(self, *args):
                pass

        mock_client.messages.stream.return_value = _BoomStream()
        mock_db = AsyncMock()

        with (
            patch("app.stages.generation.generate._get_client", return_value=mock_client),
            patch("app.stages.generation.prompts.render_prompt", return_value=("s", "u")),
        ):
            from app.stages.generation.agent import stream_agent
            with pytest.raises(RuntimeError, match="network failure"):
                await _collect_stream(stream_agent(QUERY_INPUT, [], CTX, mock_db))

    @pytest.mark.asyncio
    async def test_stream_agent_accumulates_multi_turn_tokens(self):
        """Multiple answer_token events emitted across turns when tool calls are made."""
        mock_client = MagicMock()
        tool_stream, _ = _make_stream_tool_msg("get_roster", {"team_id": 1})

        # Second turn yields text tokens
        text_stream_ctx = _MockStream(["Part1", " Part2"], MagicMock())
        text_stream_ctx._final_msg = MagicMock()
        text_stream_ctx._final_msg.stop_reason = "end_turn"
        text_stream_ctx._final_msg.content = []

        call_n = {"n": 0}

        def _side(**kw):
            call_n["n"] += 1
            return tool_stream if call_n["n"] == 1 else text_stream_ctx

        mock_client.messages.stream.side_effect = _side
        mock_db = AsyncMock()

        with (
            patch("app.stages.generation.generate._get_client", return_value=mock_client),
            patch("app.stages.generation.prompts.render_prompt", return_value=("s", "u")),
            patch("app.stages.generation.agent.dispatch_tool", new=AsyncMock(return_value={"players": []})),
        ):
            from app.stages.generation.agent import stream_agent
            events = await _collect_stream(stream_agent(QUERY_INPUT, [], CTX, mock_db))

        token_events = [e for e in events if e["type"] == "answer_token"]
        token_texts = [e["text"] for e in token_events]
        assert "Part1" in token_texts
        assert " Part2" in token_texts
