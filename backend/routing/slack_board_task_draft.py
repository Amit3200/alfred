"""LLM-assisted Slack board task drafting — title, summary, assignee."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from backend.ai.base import Message
from backend.ai.registry import LLMRouter
from backend.models.config import AlfredConfig
from backend.models.task import Task
from backend.routing.slack_board_intent import (
    DEFAULT_BOARD_SEVERITY,
    build_board_task_details,
    is_weak_board_task_title,
    normalize_board_severity,
    slack_thread_permalink,
)

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S | re.I)

BOARD_TASK_DRAFT_SYSTEM = """You draft Slack List board tasks from a Slack thread and a create-task command.

Return ONLY valid JSON:
{
  "title": "string",
  "description": "string",
  "assignee_user_id": "string",
  "severity": "string",
  "confidence": 0.0
}

Rules for title (6–120 chars):
- Action-oriented and specific to the thread (feature, merchant, incident, follow-up).
- NEVER use command fragments: "the same", "for the same", "to call me", "call me", "do the needful", "above", "it", "this".
- NEVER use a person's name alone as the title when the thread describes work for them.
- Good: "Review community replies for one-click checkout enablement"
- Good: "Call Azeem about sales pipeline"
- Bad: "the same", "to call me"

Rules for assignee_user_id:
- Use the Slack user id (U…) of the person the requester wants to OWN the task.
- Prefer ASSIGNEE HINT and phrases like "task on @Person", "assign to @Person", "for @Person to …".
- If no explicit assignee, cc'd people in the message are acceptable fallbacks.
- Do NOT assign @alfred unless they are explicitly the assignee.
- Return "" if still unclear.

Rules for description (plain text, structured):
Summary: <one sentence of what needs to be done>
Slack thread: <THREAD URL when provided>
Context:
• <bullet from thread>
• <optional second bullet>
Requested by: <requester label if known>

Rules for severity:
- Default to **Medium** when priority is unclear.
- Return High, Medium, or Low when priority/severity is clear (P0/P1→High, P2→Medium, P3→Low).
- Only return "" when the column should be omitted (rare); prefer Medium.

confidence: 0.0–1.0 for how well you understood the thread + assignee."""


@dataclass
class BoardTaskDraft:
    title: str = ""
    description: str = ""
    assignee_user_id: str = ""
    severity: str = ""
    confidence: float = 0.0


def _parse_draft_json(content: str) -> dict[str, Any] | None:
    text = (content or "").strip()
    if not text:
        return None
    match = _JSON_BLOCK_RE.search(text)
    blob = match.group(1) if match else text
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def draft_board_task_from_thread(
    *,
    config: AlfredConfig,
    task: Task,
    messages_text: str,
    request_text: str,
    thread_url: str = "",
    hint_assignee_user_id: str = "",
    hint_title: str = "",
    mention_labels: dict[str, str] | None = None,
    data_dir: Any = None,
) -> BoardTaskDraft | None:
    """Use LLM to produce title, structured description, and assignee from thread context."""
    if not (messages_text or request_text).strip():
        return None
    try:
        from backend.ai.registry import LLMRouter
        from backend.ai.routing import resolve_llm_route

        router = LLMRouter.from_config(config, data_dir=data_dir)
        _, provider, model = resolve_llm_route(config.ai, "basic_chat", router=router)
    except Exception as exc:
        logger.warning("Board task draft: LLM unavailable: %s", exc)
        return None

    requester_label = (mention_labels or {}).get(task.user_id or "", task.user_id or "requester")
    user_prompt = "\n".join(
        [
            f"REQUEST (cleaned): {request_text.strip()}",
            f"RAW REQUEST: {(task.raw_text or '').strip()}",
            f"REQUESTER USER ID: {task.user_id or 'unknown'}",
            f"REQUESTER LABEL: {requester_label}",
            f"ASSIGNEE HINT USER ID: {hint_assignee_user_id or '(none)'}",
            f"REGEX TITLE HINT: {hint_title or '(none)'}",
            f"MENTION MAP: {json.dumps(mention_labels or {}, ensure_ascii=False)}",
            f"THREAD URL: {thread_url or '(none)'}",
            "",
            "THREAD MESSAGES:",
            (messages_text or "").strip()[:12000],
        ]
    )

    try:
        response = provider.chat(
            [
                Message(role="system", content=BOARD_TASK_DRAFT_SYSTEM),
                Message(role="user", content=user_prompt),
            ],
            model=model or None,
        )
    except Exception as exc:
        logger.warning("Board task draft LLM call failed: %s", exc)
        return None

    parsed = _parse_draft_json(response.content or "")
    if not parsed:
        return None

    title = str(parsed.get("title") or "").strip()[:200]
    if is_weak_board_task_title(title):
        title = ""

    description = str(parsed.get("description") or "").strip()
    if not description and thread_url:
        description = build_board_task_details(
            messages_text=messages_text,
            channel_id=task.channel_id or "",
            thread_ts=task.thread_ts or "",
            task_title=title or hint_title,
        )

    assignee = str(parsed.get("assignee_user_id") or "").strip()
    if assignee and not re.fullmatch(r"U[A-Z0-9]+", assignee):
        assignee = ""

    severity = normalize_board_severity(str(parsed.get("severity") or ""))
    if not severity:
        severity = DEFAULT_BOARD_SEVERITY
    try:
        confidence = float(parsed.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0

    if not title and not description:
        return None

    return BoardTaskDraft(
        title=title,
        description=description[:4000],
        assignee_user_id=assignee,
        severity=severity,
        confidence=max(0.0, min(confidence, 1.0)),
    )
