"""Final-answer synthesis when the agent loop hits iteration limits."""

from __future__ import annotations

import logging

from backend.ai.base import LLMProvider, Message
from backend.routing.git.direct import strip_text_tool_markup

logger = logging.getLogger(__name__)


def synthesize_final_answer(
    provider: LLMProvider,
    conversation: list[Message],
    *,
    model: str | None = None,
) -> str | None:
    """One tool-free LLM pass to answer from gathered tool results only."""
    synthesis_messages = [
        *conversation,
        Message(
            role="user",
            content=(
                "You reached the investigation step limit. Using ONLY the tool results "
                "and context above, give the user a direct answer. "
                "Do not invent URLs, ticket keys, counts, or file paths. "
                "If evidence is incomplete, summarize what was verified and what remains unclear."
            ),
        ),
    ]
    try:
        response = provider.chat(synthesis_messages, model=model)
    except Exception:
        logger.exception("Synthesis pass failed")
        return None

    if response.tool_calls:
        return None

    content = strip_text_tool_markup((response.content or "").strip()).strip()
    return content or None
