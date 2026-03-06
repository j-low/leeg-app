# Stage 3: Generation, Tool Calling & Agentic Loops
# Public re-exports so callers use `from app.stages.generation import ...`
from app.stages.generation.agent import MAX_ITERATIONS, run_agent
from app.stages.generation.generate import (
    call_llm,
    extract_text,
    extract_tool_uses,
    generate_response,
)
from app.stages.generation.prompts import render_prompt
from app.stages.generation.tools import TOOL_SCHEMAS, dispatch_tool

__all__ = [
    "run_agent",
    "MAX_ITERATIONS",
    "generate_response",
    "call_llm",
    "extract_text",
    "extract_tool_uses",
    "render_prompt",
    "TOOL_SCHEMAS",
    "dispatch_tool",
]
