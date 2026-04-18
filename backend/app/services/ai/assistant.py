"""
AI Assistant service — powered by OpenAI.

Provides:
  - Command explanation
  - Error debugging
  - Step-by-step suggestions
  - DevOps coaching
  - Lab hint generation

Every call streams tokens back to the caller so the frontend can display
a typewriter effect without waiting for full completion.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Literal

import structlog
from openai import AsyncOpenAI

from app.core.config import settings

logger = structlog.get_logger(__name__)

_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

AssistantMode = Literal["explain", "debug", "hint", "coach", "general"]

SYSTEM_PROMPTS: dict[AssistantMode, str] = {
    "explain": (
        "You are OpsMind AI, an expert DevOps engineer. "
        "Explain the given shell command or concept clearly and concisely. "
        "Include: what it does, common flags, potential pitfalls, and a real-world use case. "
        "Format with Markdown."
    ),
    "debug": (
        "You are OpsMind AI, an expert SRE debugging assistant. "
        "Analyze the error output and provide: "
        "1) Root cause analysis, "
        "2) Step-by-step fix, "
        "3) How to prevent it in future. "
        "Be direct and practical."
    ),
    "hint": (
        "You are OpsMind AI, a lab coach. "
        "The user is stuck on a lab task. "
        "Give a HINT — not the full answer — that nudges them in the right direction. "
        "Keep it to 2-3 sentences. Do NOT reveal the exact command."
    ),
    "coach": (
        "You are OpsMind AI, a senior DevOps mentor. "
        "Provide structured, actionable coaching. "
        "Reference industry best practices, tools, and real production scenarios. "
        "Be encouraging but technically rigorous."
    ),
    "general": (
        "You are OpsMind AI, an AI-powered DevOps, SRE, and Cloud assistant. "
        "You have deep expertise in Kubernetes, Linux, CI/CD, networking, security, and IaC. "
        "Be helpful, precise, and use examples."
    ),
}


async def stream_response(
    user_message: str,
    mode: AssistantMode = "general",
    context: str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Stream AI response tokens.

    Args:
        user_message: The user's question or input
        mode: Controls the system prompt behaviour
        context: Optional context (e.g. terminal output, error logs)
        conversation_history: Prior messages for multi-turn conversations
    """
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPTS[mode]}
    ]

    if conversation_history:
        messages.extend(conversation_history[-10:])  # keep last 10 turns

    if context:
        messages.append({
            "role": "user",
            "content": f"<context>\n{context[:3000]}\n</context>\n\n{user_message}",
        })
    else:
        messages.append({"role": "user", "content": user_message})

    logger.info("ai_request", mode=mode, tokens_approx=len(user_message) // 4)

    stream = await _client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=messages,  # type: ignore[arg-type]
        max_tokens=settings.AI_MAX_TOKENS,
        temperature=settings.AI_TEMPERATURE,
        stream=True,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


async def get_lab_hint(
    lab_title: str,
    task_description: str,
    terminal_history: str,
) -> AsyncGenerator[str, None]:
    """Convenience wrapper for in-lab hints."""
    context = (
        f"Lab: {lab_title}\n"
        f"Task: {task_description}\n"
        f"User's recent terminal output:\n{terminal_history[-2000:]}"
    )
    async for token in stream_response(
        user_message="I'm stuck. Give me a hint for this task.",
        mode="hint",
        context=context,
    ):
        yield token


async def explain_command(command: str) -> AsyncGenerator[str, None]:
    async for token in stream_response(
        user_message=f"Explain this command: `{command}`",
        mode="explain",
    ):
        yield token


async def debug_error(error_output: str) -> AsyncGenerator[str, None]:
    async for token in stream_response(
        user_message="Help me debug this error.",
        mode="debug",
        context=error_output,
    ):
        yield token
