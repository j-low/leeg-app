"""
Stage 3: LLM call assembly and initial response parsing.

Assembles the Anthropic API call from Stage 1 + Stage 2 outputs, calls
Claude Haiku with the registered tool schemas, and returns the raw response
for the agent loop in agent.py to process.

Responsibilities (only):
  - Render the prompt via prompts.render_prompt()
  - Build the messages list
  - Call the Anthropic API
  - Return the Message object (stop_reason, content blocks)

The agent loop (agent.py) handles tool dispatch and multi-turn iteration.
"""
import logging

import anthropic

from app.config import settings
from app.schemas.pipeline import StructuredInput
from app.stages.generation.prompts import render_prompt
from app.stages.generation.tools import TOOL_SCHEMAS

log = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 1024


def _get_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


async def call_llm(
    messages: list[dict],
    system: str,
) -> anthropic.types.Message:
    """Make a single Anthropic API call and return the Message object.

    Args:
        messages: Full conversation history in Anthropic format
                  [{"role": "user"|"assistant", "content": ...}].
        system:   System prompt string.

    Returns:
        anthropic.types.Message with .stop_reason and .content.
    """
    client = _get_client()
    response = await client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=system,
        tools=TOOL_SCHEMAS,
        tool_choice={"type": "auto"},
        messages=messages,
    )
    log.debug(
        "generate.call_llm stop_reason=%s input_tokens=%d output_tokens=%d",
        response.stop_reason,
        response.usage.input_tokens,
        response.usage.output_tokens,
    )
    return response


async def generate_response(
    structured_input: StructuredInput,
    rag_context: list[dict],
    context: dict,
) -> anthropic.types.Message:
    """Render prompt and make the first LLM call.

    This is the entry point called by the agent loop for the first turn.
    Subsequent turns (after tool results are fed back) call call_llm()
    directly with the accumulated messages list.

    Args:
        structured_input: Stage 1 output (intent, entities, raw_text).
        rag_context:      Stage 2 output (retrieved + reranked chunks).
        context:          Request envelope (team_id, channel, from_phone).

    Returns:
        anthropic.types.Message — the LLM's first response.
    """
    system, user_msg = render_prompt(structured_input, rag_context, context)
    messages: list[dict] = [{"role": "user", "content": user_msg}]

    log.info(
        "generate.first_call intent=%s team_id=%s rag_chunks=%d",
        structured_input.intent,
        context.get("team_id"),
        len(rag_context),
    )
    return await call_llm(messages, system)


def extract_text(response: anthropic.types.Message) -> str:
    """Extract concatenated text content from a Message.

    Returns empty string if the response contains no text blocks
    (e.g. pure tool_use response).
    """
    return "\n".join(
        block.text
        for block in response.content
        if block.type == "text"
    )


def extract_tool_uses(response: anthropic.types.Message) -> list[dict]:
    """Extract all tool_use blocks from a Message.

    Returns:
        List of dicts: [{id, name, input}] — ready to pass to dispatch_tool().
    """
    return [
        {"id": block.id, "name": block.name, "input": block.input}
        for block in response.content
        if block.type == "tool_use"
    ]
