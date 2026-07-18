"""Heuristic thread message ranking for long Slack threads."""

from __future__ import annotations

import re
from typing import Any

from backend.formatting.slack_messages import extract_message_text
from backend.orchestrator.policy import prune_context

_STACK_RE = re.compile(r"Traceback \(most recent call last\)|Exception:|Error:", re.IGNORECASE)
_FILE_PATH_RE = re.compile(
    r"(?:[\w.-]+/)+[\w.-]+\.(?:py|js|ts|tsx|go|java|rb|yml|yaml|json|md|sql)\b"
)
_ERROR_CODE_RE = re.compile(r"\b(?:E[A-Z]{3,}|[A-Z_]{3,}\d{2,})\b")
_URL_RE = re.compile(r"https?://[^\s>]+")
_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "that",
        "this",
        "with",
        "from",
        "have",
        "what",
        "when",
        "where",
        "alfred",
        "please",
        "thanks",
        "thank",
    }
)


def _intent_tokens(intent: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_]{3,}", (intent or "").lower())
        if token not in _STOPWORDS
    }


def score_thread_message(
    message: dict[str, Any],
    *,
    intent: str,
    index: int,
    total: int,
    requesting_user_id: str = "",
) -> float:
    text = extract_message_text(message) or ""
    if not text.strip():
        return 0.0

    score = 0.0
    score += ((index + 1) / max(total, 1)) * 2.0

    intent_tokens = _intent_tokens(intent)
    message_tokens = _intent_tokens(text)
    score += len(intent_tokens & message_tokens) * 1.5

    if _STACK_RE.search(text):
        score += 5.0
    if _FILE_PATH_RE.search(text):
        score += 3.0
    if _ERROR_CODE_RE.search(text):
        score += 2.0
    if _URL_RE.search(text):
        score += 1.0
    lower = text.lower()
    if "github.com" in lower or "gitlab" in lower:
        score += 2.0
    if message.get("attachments"):
        score += 2.0
    if requesting_user_id and message.get("user") == requesting_user_id:
        score += 1.5
    return score


def rank_thread_messages(
    messages: list[dict[str, Any]],
    intent: str,
    *,
    requesting_user_id: str = "",
    top_n: int = 15,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (kept, omitted) messages sorted by relevance then original order."""
    if top_n <= 0 or len(messages) <= top_n:
        return messages, []

    scored = [
        (
            score_thread_message(
                message,
                intent=intent,
                index=index,
                total=len(messages),
                requesting_user_id=requesting_user_id,
            ),
            index,
            message,
        )
        for index, message in enumerate(messages)
    ]
    scored.sort(key=lambda item: (-item[0], item[1]))
    kept_indices = sorted(index for _, index, _ in scored[:top_n])
    kept_set = set(kept_indices)
    kept = [messages[index] for index in kept_indices]
    omitted = [messages[index] for index in range(len(messages)) if index not in kept_set]
    return kept, omitted


def format_ranked_thread_section(
    kept: list[dict[str, Any]],
    omitted: list[dict[str, Any]],
    *,
    user_names: dict[str, str] | None = None,
) -> str | None:
    from backend.integrations.slack.context import messages_to_text

    lines: list[str] = []
    main = messages_to_text(kept, user_names=user_names)
    if main:
        lines.append(main)
    if omitted:
        snippets: list[str] = []
        for message in omitted[:8]:
            text = prune_context((extract_message_text(message) or "").strip().replace("\n", " "))
            if not text:
                continue
            snippets.append(text[:80] + ("…" if len(text) > 80 else ""))
        if snippets:
            lines.append(
                f"[{len(omitted)} earlier thread message(s) omitted — snippets: "
                + "; ".join(snippets)
                + "]"
            )
    return "\n\n".join(lines) if lines else None
