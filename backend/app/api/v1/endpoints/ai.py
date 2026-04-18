"""
AI Assistant endpoints.
All responses are server-sent events (SSE) for streaming token delivery.
"""
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.v1.dependencies import get_current_user
from app.db.models.user import User
from app.services.ai.assistant import (
    AssistantMode,
    debug_error,
    explain_command,
    get_lab_hint,
    stream_response,
)

router = APIRouter(prefix="/ai", tags=["ai"])


class ChatRequest(BaseModel):
    message: str
    mode: AssistantMode = "general"
    context: str | None = None
    history: list[dict[str, str]] | None = None


class ExplainRequest(BaseModel):
    command: str


class DebugRequest(BaseModel):
    error_output: str


class HintRequest(BaseModel):
    lab_title: str
    task_description: str
    terminal_history: str = ""


def _sse_stream(generator):
    """Wrap an async generator as SSE."""
    async def event_stream():
        async for token in generator:
            yield f"data: {token}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/chat")
async def chat(
    body: ChatRequest,
    _: User = Depends(get_current_user),
) -> StreamingResponse:
    """General-purpose AI chat with streaming SSE response."""
    gen = stream_response(
        user_message=body.message,
        mode=body.mode,
        context=body.context,
        conversation_history=body.history,
    )
    return _sse_stream(gen)


@router.post("/explain")
async def explain(
    body: ExplainRequest,
    _: User = Depends(get_current_user),
) -> StreamingResponse:
    """Explain a shell command."""
    return _sse_stream(explain_command(body.command))


@router.post("/debug")
async def debug(
    body: DebugRequest,
    _: User = Depends(get_current_user),
) -> StreamingResponse:
    """Debug an error output."""
    return _sse_stream(debug_error(body.error_output))


@router.post("/hint")
async def hint(
    body: HintRequest,
    _: User = Depends(get_current_user),
) -> StreamingResponse:
    """Get a lab task hint without revealing the answer."""
    gen = get_lab_hint(
        lab_title=body.lab_title,
        task_description=body.task_description,
        terminal_history=body.terminal_history,
    )
    return _sse_stream(gen)
