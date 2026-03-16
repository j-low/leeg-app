"""SSE streaming chat endpoint for the dashboard channel.

POST /api/chat/stream — requires captain auth. Accepts a natural language
input, injects channel="dashboard" into context, and delegates to
run_pipeline_stream(). Each yielded event dict is serialized as an SSE
data line and flushed immediately to the client.

Event types (defined by run_pipeline_stream):
  {"type": "answer_token", "text": str}
  {"type": "tool_start",   "name": str, "input": dict}
  {"type": "tool_result",  "name": str, "result": any}
  {"type": "done",         "text_for_user": str, "mutations": list}
  {"type": "error",        "message": str}
  {"type": "ping"}           -- keepalive (injected by this layer)
"""
import asyncio
import json
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_captain
from app.db import get_db
from app.models.user import User
from app.pipeline import run_pipeline_stream

router = APIRouter(prefix="/api/chat", tags=["chat"])

KEEPALIVE_INTERVAL = 15  # seconds between ping frames when stream is idle


class ChatStreamRequest(BaseModel):
    input: str
    context: dict = {}


@router.post("/stream")
async def chat_stream(
    request: ChatStreamRequest,
    current_user: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    """Stream pipeline events to the dashboard client as SSE."""
    context = {**request.context, "channel": "dashboard"}

    async def event_generator():
        pipeline_gen = run_pipeline_stream(request.input, context, db)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        pipeline_gen.__anext__(),
                        timeout=KEEPALIVE_INTERVAL,
                    )
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") in ("done", "error"):
                        break
                except asyncio.TimeoutError:
                    # No event for KEEPALIVE_INTERVAL seconds — send ping to
                    # keep the HTTP connection alive through proxies.
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"
                except StopAsyncIteration:
                    break
        except asyncio.CancelledError:
            pass  # client disconnected — clean exit
        finally:
            await pipeline_gen.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
            "Connection": "keep-alive",
        },
    )
