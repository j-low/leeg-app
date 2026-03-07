"""
Stage 3: LangGraph ReAct agent loop.

Implements the reason → act → observe → reason cycle using LangGraph's
StateGraph. Claude Haiku drives reasoning; tool results are fed back as
tool_result blocks in the next LLM turn.

Safety bounds:
  - MAX_ITERATIONS = 5   (prevents runaway loops)
  - STEP_TIMEOUT   = 30s (per LLM call + tool execution)
  - TOTAL_TIMEOUT  = 120s (entire agent run)

State machine:
  START -> call_llm -> (tool_use?) -> execute_tools -> call_llm -> ...
                    -> (end_turn?)  -> END

The agent loop terminates when:
  (a) stop_reason == "end_turn"  (Claude is done)
  (b) iteration count hits MAX_ITERATIONS
  (c) stop_reason == "max_tokens"  (treated as a final answer)

run_agent() returns a dict:
  {
    "answer":             str,   # final text from Claude
    "tool_calls":         list,  # all tool calls made [{name, input, result}]
    "iterations":         int,   # number of LLM turns
    "stop_reason":        str,   # last stop_reason from Claude
    "tokens_prompt":      int,   # accumulated input tokens across all turns
    "tokens_completion":  int,   # accumulated output tokens across all turns
  }

stream_agent() is the streaming variant (see docstring below).
"""
import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.pipeline import StructuredInput
from app.stages.generation.generate import call_llm, extract_text, extract_tool_uses, generate_response
from app.stages.generation.tools import dispatch_tool

log = logging.getLogger(__name__)

MAX_ITERATIONS = 5
STEP_TIMEOUT = 30    # seconds per LLM call + tool round-trip
TOTAL_TIMEOUT = 120  # seconds for the entire agent run


# ── LangGraph state ───────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages:           list[dict]   # full conversation history
    system:             str          # system prompt (constant across turns)
    tool_calls:         list[dict]   # audit log: [{name, input, result}]
    iterations:         int          # current iteration count
    answer:             str          # final text answer (set on termination)
    stop_reason:        str          # last Claude stop_reason
    tokens_prompt:      int          # accumulated input tokens across all turns
    tokens_completion:  int          # accumulated output tokens across all turns
    db:                 Any          # AsyncSession (not serialisable; held in state)


# ── Graph nodes ───────────────────────────────────────────────────────────────

async def _node_call_llm(state: AgentState) -> AgentState:
    """Call Claude with the current messages history."""
    response = await asyncio.wait_for(
        call_llm(state["messages"], state["system"]),
        timeout=STEP_TIMEOUT,
    )

    # Append assistant's reply to message history (required by Anthropic multi-turn format)
    updated_messages = list(state["messages"]) + [
        {"role": "assistant", "content": response.content}
    ]

    usage = getattr(response, "usage", None)
    return {
        **state,
        "messages":          updated_messages,
        "stop_reason":       response.stop_reason,
        "iterations":        state["iterations"] + 1,
        # Stash the answer if this turns out to be the final turn
        "answer":            extract_text(response) or state.get("answer", ""),
        # Accumulate token counts across all iterations
        "tokens_prompt":     state.get("tokens_prompt", 0) + (usage.input_tokens if usage else 0),
        "tokens_completion":  state.get("tokens_completion", 0) + (usage.output_tokens if usage else 0),
    }


async def _node_execute_tools(state: AgentState) -> AgentState:
    """Execute all tool_use blocks from the last assistant message and feed results back."""
    last_message = state["messages"][-1]
    tool_uses = extract_tool_uses_from_content(last_message["content"])

    tool_results = []
    tool_call_log = list(state["tool_calls"])

    for tu in tool_uses:
        try:
            result = await asyncio.wait_for(
                dispatch_tool(tu["name"], tu["input"], state["db"]),
                timeout=STEP_TIMEOUT,
            )
            tool_call_log.append({"name": tu["name"], "input": tu["input"], "result": result})
            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": tu["id"],
                "content":     json.dumps(result),
            })
            log.info("agent.tool_done name=%s", tu["name"])
        except Exception as exc:
            log.warning("agent.tool_error name=%s error=%s", tu["name"], exc)
            tool_call_log.append({"name": tu["name"], "input": tu["input"], "error": str(exc)})
            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": tu["id"],
                "content":     json.dumps({"error": str(exc)}),
                "is_error":    True,
            })

    # Append tool results as a user turn (Anthropic multi-turn tool use format)
    updated_messages = list(state["messages"]) + [
        {"role": "user", "content": tool_results}
    ]

    return {
        **state,
        "messages":   updated_messages,
        "tool_calls": tool_call_log,
    }


# ── Routing ───────────────────────────────────────────────────────────────────

def _should_continue(state: AgentState) -> str:
    """Decide whether to execute tools, end, or hard-stop on max iterations."""
    if state["iterations"] >= MAX_ITERATIONS:
        log.warning("agent.max_iterations_reached iterations=%d", state["iterations"])
        return END

    stop_reason = state.get("stop_reason", "")
    if stop_reason == "tool_use":
        return "execute_tools"

    # end_turn, max_tokens, or anything else → done
    return END


# ── Graph assembly ────────────────────────────────────────────────────────────

def _build_graph() -> Any:
    graph = StateGraph(AgentState)
    graph.add_node("call_llm",      _node_call_llm)
    graph.add_node("execute_tools", _node_execute_tools)

    graph.add_edge(START,           "call_llm")
    graph.add_conditional_edges(
        "call_llm",
        _should_continue,
        {"execute_tools": "execute_tools", END: END},
    )
    graph.add_edge("execute_tools", "call_llm")

    return graph.compile()


_graph = _build_graph()


# ── Helper ────────────────────────────────────────────────────────────────────

def extract_tool_uses_from_content(content: Any) -> list[dict]:
    """Extract tool_use blocks from an assistant message content field.

    Content may be a list of block objects (from the Anthropic SDK) or a
    list of dicts (when reconstructed from JSON for tests).
    """
    results = []
    if not isinstance(content, list):
        return results
    for block in content:
        # SDK objects have .type; dicts have ["type"]
        block_type = getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else None)
        if block_type == "tool_use":
            results.append({
                "id":    getattr(block, "id",    None) or block.get("id"),
                "name":  getattr(block, "name",  None) or block.get("name"),
                "input": getattr(block, "input", None) or block.get("input", {}),
            })
    return results


# ── Public API ────────────────────────────────────────────────────────────────

async def run_agent(
    structured_input: StructuredInput,
    rag_context: list[dict],
    context: dict,
    db: AsyncSession,
) -> dict:
    """Run the full ReAct agent loop and return the final result.

    Args:
        structured_input: Stage 1 output.
        rag_context:      Stage 2 output.
        context:          Request envelope (team_id, channel, from_phone).
        db:               Active AsyncSession for tool DB access.

    Returns:
        {
            "answer":      str   — final text response to send back,
            "tool_calls":  list  — audit log of all tool calls made,
            "iterations":  int   — number of LLM turns,
            "stop_reason": str   — Claude's last stop_reason,
        }
    """
    from app.stages.generation.prompts import render_prompt
    system, user_msg = render_prompt(structured_input, rag_context, context)

    log.info(
        "agent.start intent=%s team_id=%s",
        structured_input.intent,
        context.get("team_id"),
    )

    initial_state: AgentState = {
        "messages":          [{"role": "user", "content": user_msg}],
        "system":            system,
        "tool_calls":        [],
        "iterations":        0,
        "answer":            "",
        "stop_reason":       "",
        "tokens_prompt":     0,
        "tokens_completion": 0,
        "db":                db,
    }

    try:
        final_state = await asyncio.wait_for(
            _graph.ainvoke(initial_state),
            timeout=TOTAL_TIMEOUT,
        )
    except asyncio.TimeoutError:
        log.error("agent.total_timeout_exceeded")
        return {
            "answer":      "Sorry, the request took too long. Please try again.",
            "tool_calls":  [],
            "iterations":  MAX_ITERATIONS,
            "stop_reason": "timeout",
        }

    log.info(
        "agent.done iterations=%d tool_calls=%d stop_reason=%s",
        final_state["iterations"],
        len(final_state["tool_calls"]),
        final_state["stop_reason"],
    )

    return {
        "answer":            final_state["answer"],
        "tool_calls":        final_state["tool_calls"],
        "iterations":        final_state["iterations"],
        "stop_reason":       final_state["stop_reason"],
        "tokens_prompt":     final_state.get("tokens_prompt", 0),
        "tokens_completion": final_state.get("tokens_completion", 0),
    }


async def stream_agent(
    structured_input: StructuredInput,
    rag_context: list[dict],
    context: dict,
    db: AsyncSession,
) -> AsyncGenerator[dict, None]:
    """Streaming variant of run_agent for the dashboard SSE channel.

    Yields typed event dicts as the agent works. Does NOT yield the final
    "done" event — the caller (run_pipeline_stream) handles post-processing
    and emits "done" after accumulating the answer.

    Event types:
        {type: "answer_token", text: str}   — streamed text token from Claude
        {type: "tool_start",   name: str, input: dict}  — tool dispatched
        {type: "tool_result",  name: str, result: any}  — tool execution complete

    Never raises: asyncio.TimeoutError yields a fallback answer_token then
    returns; other exceptions are re-raised for run_pipeline_stream to catch
    and convert to {type: "error"} events.
    """
    from app.stages.generation.generate import _get_client, MODEL, MAX_TOKENS, TOOL_SCHEMAS

    from app.stages.generation.prompts import render_prompt
    system, user_msg = render_prompt(structured_input, rag_context, context)
    messages = [{"role": "user", "content": user_msg}]
    client = _get_client()

    log.info(
        "stream_agent.start intent=%s team_id=%s",
        structured_input.intent,
        context.get("team_id"),
    )

    iterations = 0
    try:
        while iterations < MAX_ITERATIONS:
            iterations += 1

            try:
                async with client.messages.stream(
                    model=MODEL,
                    system=system,
                    messages=messages,
                    tools=TOOL_SCHEMAS,
                    max_tokens=MAX_TOKENS,
                ) as stream:
                    # Yield text tokens as they arrive
                    async for text in stream.text_stream:
                        yield {"type": "answer_token", "text": text}

                    final_msg = await stream.get_final_message()

            except asyncio.TimeoutError:
                log.error("stream_agent.step_timeout iteration=%d", iterations)
                yield {"type": "answer_token", "text": "Sorry, the request took too long."}
                return

            # Append assistant turn to conversation history
            messages.append({"role": "assistant", "content": final_msg.content})

            if final_msg.stop_reason != "tool_use":
                # end_turn or max_tokens — done streaming
                break

            # ── Execute tool calls ────────────────────────────────────────────
            tool_results = []
            for block in final_msg.content:
                if getattr(block, "type", None) != "tool_use":
                    continue

                yield {"type": "tool_start", "name": block.name, "input": block.input}

                try:
                    result = await asyncio.wait_for(
                        dispatch_tool(block.name, block.input, db),
                        timeout=STEP_TIMEOUT,
                    )
                    yield {"type": "tool_result", "name": block.name, "result": result}
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     json.dumps(result),
                    })
                except Exception as exc:
                    log.warning("stream_agent.tool_error name=%s error=%s", block.name, exc)
                    error_payload = {"error": str(exc)}
                    yield {"type": "tool_result", "name": block.name, "result": error_payload}
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     json.dumps(error_payload),
                        "is_error":    True,
                    })

            messages.append({"role": "user", "content": tool_results})

        if iterations >= MAX_ITERATIONS:
            log.warning("stream_agent.max_iterations_reached iterations=%d", iterations)

    except Exception:
        # Re-raise — run_pipeline_stream catches and yields {type: "error"}
        raise
