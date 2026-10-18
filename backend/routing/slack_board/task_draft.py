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
from backend.routing.slack_board.intent import (
    DEFAULT_BOARD_SEVERITY,
    build_board_task_details,
    extract_title_from_summary,
    humanize_board_task_text,
    is_weak_board_task_title,
    normalize_board_severity,
    references_thread_context,
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

## Title (List item Name — most important field)
- Write the title FIRST. It is shown as the task name on the board.
- 6–120 chars, action-oriented, specific to the THREAD MESSAGES (not the @alfred command).
- When the user says "for the above" / "the same" / "this", IGNORE those words — infer work from the thread.
- The title MUST match the action in your Summary line (same meaning, title is shorter).
- NEVER use command fragments: "the same", "for the same", "to call me", "above", "the above", "the above?", "it", "this".
- Good: "Share partnership sheet with Aditya for agency client names"
- Good: "Review community replies for one-click checkout enablement"
- Bad: "the above?", "the same", "to call me"

## assignee_user_id
- Slack user id (U…) of whoever must **do the work**, not who asked @alfred, not the recipient.
- Thread root "@Riya please share … with @Aditya" → assign Riya (U… from MENTION MAP), not Aditya.
- Use ASSIGNEE HINT when provided. Cc'd people are fallback only when no clear owner.

## description (structured plain text — human readable)
- Use @DisplayName for people (from MENTION MAP). NEVER write raw U… ids in description.
- Summary: <one sentence — same action as title>
Slack thread: <THREAD URL when provided>
Context:
• <bullet from thread, use @names>
Requested by: @<requester display name>

## severity
- Default Medium when unclear. P0/P1→High, P2→Medium, P3→Low.

confidence: 0.0–1.0 for thread + assignee understanding."""


BOARD_TASK_BATCH_DRAFT_SYSTEM = """You draft Slack List board tasks from a numbered source list plus optional thread context.

Return ONLY valid JSON:
{
  "tasks": [
    {
      "source_title": "string",
      "title": "string",
      "description": "string",
      "assignee_user_id": "string",
      "severity": "string"
    }
  ]
}

## Count and order
- Produce exactly one object per SOURCE ITEM, in the same order. Never add extra tasks.
- Copy source_title from the source item so we can align results.
- Ignore Alfred bot replies, governance/approval text, and board confirmation metadata
  (List/Status/Severity/Assignee/Record/Open List, TS- ids already created).

## Title (List item Name)
- 6–120 chars, action-oriented, specific to THAT source item.
- Keep merchant/product names (Everaw, Mishmash, AuraByNoureya, Snapchat, UPI, COD).
- Polish grammar; do not merge two items into one title.
- Good: "Add exit reason to export file"
- Good: "Limit cart discount for Everaw"
- Bad: "all the above issues", "the above", a dump of the full list.

## description (structured plain text — THIS item only)
- Use @DisplayName for people (from MENTION MAP). NEVER write raw U… ids.
- Summary: <one sentence for this item — same action as title>
Slack thread: <THREAD URL when provided>
Context:
• <1–3 bullets about THIS item only; merchant/product constraints if present>
Requested by: @<requester display name>
- Do NOT paste the full numbered list into every description.

## assignee_user_id / severity
- Slack user id (U…) of whoever must do the work, else empty.
- Default Medium when unclear. P0/P1→High, P2→Medium, P3→Low.
"""


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


def _resolve_draft_title(
    parsed_title: str,
    description: str,
    *,
    hint_title: str = "",
    request_text: str = "",
) -> str:
    title = (parsed_title or "").strip()[:200]
    if title and not is_weak_board_task_title(title):
        return title
    from_summary = extract_title_from_summary(description)
    if from_summary:
        return from_summary
    if hint_title and not is_weak_board_task_title(hint_title):
        return hint_title[:200]
    if references_thread_context(request_text) and description:
        from_summary = extract_title_from_summary(description)
        if from_summary:
            return from_summary
    return ""


def _requester_label(task: Task, mention_labels: dict[str, str]) -> str:
    name = (mention_labels.get(task.user_id or "") or "").strip()
    return f"@{name}" if name else "requester"


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

    labels = dict(mention_labels or {})
    requester_label = _requester_label(task, labels)
    assignee_hint = hint_assignee_user_id or "(none)"
    if hint_assignee_user_id and labels.get(hint_assignee_user_id):
        assignee_hint = f"{hint_assignee_user_id} (@{labels[hint_assignee_user_id]})"
    regex_hint = hint_title or "(none)"
    if hint_title and is_weak_board_task_title(hint_title):
        regex_hint = f"{hint_title} (IGNORE — derive title from thread)"
    user_prompt = "\n".join(
        [
            f"REQUEST (cleaned): {request_text.strip()}",
            f"RAW REQUEST: {(task.raw_text or '').strip()}",
            f"REQUESTER: {requester_label}",
            f"ASSIGNEE HINT: {assignee_hint}",
            f"REGEX TITLE HINT: {regex_hint}",
            f"MENTION MAP (U id → display name): {json.dumps(labels, ensure_ascii=False)}",
            f"THREAD URL: {thread_url or '(none)'}",
            "",
            "Generate BOTH title and description from THREAD MESSAGES.",
            "Use @DisplayName in description — never raw U ids.",
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

    description = str(parsed.get("description") or "").strip()
    if not description:
        description = build_board_task_details(
            messages_text=messages_text,
            channel_id=task.channel_id or "",
            thread_ts=task.thread_ts or "",
            task_title="",
            requester_user_id=task.user_id or "",
            mention_labels=labels,
        )
    description = humanize_board_task_text(description, labels)

    title = _resolve_draft_title(
        str(parsed.get("title") or ""),
        description,
        hint_title=hint_title,
        request_text=request_text,
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


def _fallback_item_description(
    title: str,
    *,
    thread_url: str = "",
    requester_label: str = "",
) -> str:
    parts = [f"Summary: {title}"]
    if thread_url:
        parts.append(f"Slack thread: {thread_url}")
    if requester_label:
        parts.append(f"Requested by: {requester_label}")
    return "\n".join(parts)


def _fallback_batch_drafts(
    titles: list[str],
    *,
    thread_url: str = "",
    requester_label: str = "",
    hint_assignee_user_id: str = "",
    default_severity: str = DEFAULT_BOARD_SEVERITY,
) -> list[BoardTaskDraft]:
    drafts: list[BoardTaskDraft] = []
    for title in titles:
        cleaned = (title or "").strip()[:200]
        if not cleaned:
            continue
        drafts.append(
            BoardTaskDraft(
                title=cleaned,
                description=_fallback_item_description(
                    cleaned,
                    thread_url=thread_url,
                    requester_label=requester_label,
                ),
                assignee_user_id=hint_assignee_user_id,
                severity=default_severity or DEFAULT_BOARD_SEVERITY,
            )
        )
    return drafts


def _parse_batch_task_rows(content: str) -> list[dict[str, Any]]:
    parsed = _parse_draft_json(content)
    if parsed is None:
        return []
    rows = parsed.get("tasks")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    if "title" in parsed or "description" in parsed:
        return [parsed]
    return []


def draft_board_tasks_batch_from_thread(
    *,
    config: AlfredConfig,
    task: Task,
    item_titles: list[str],
    messages_text: str = "",
    request_text: str = "",
    thread_url: str = "",
    hint_assignee_user_id: str = "",
    mention_labels: dict[str, str] | None = None,
    default_severity: str = "",
    data_dir: Any = None,
) -> list[BoardTaskDraft]:
    """Draft one structured task per numbered source item (single LLM call)."""
    labels = dict(mention_labels or {})
    requester_label = _requester_label(task, labels)
    fallbacks = _fallback_batch_drafts(
        item_titles,
        thread_url=thread_url,
        requester_label=requester_label,
        hint_assignee_user_id=hint_assignee_user_id,
        default_severity=default_severity or DEFAULT_BOARD_SEVERITY,
    )
    if len(fallbacks) < 2:
        return fallbacks

    try:
        from backend.ai.routing import resolve_llm_route

        router = LLMRouter.from_config(config, data_dir=data_dir)
        _, provider, model = resolve_llm_route(config.ai, "basic_chat", router=router)
    except Exception as exc:
        logger.warning("Board batch draft: LLM unavailable: %s", exc)
        return fallbacks

    assignee_hint = hint_assignee_user_id or "(none)"
    if hint_assignee_user_id and labels.get(hint_assignee_user_id):
        assignee_hint = f"{hint_assignee_user_id} (@{labels[hint_assignee_user_id]})"
    numbered = "\n".join(f"{idx}. {title}" for idx, title in enumerate(item_titles, start=1) if title.strip())
    user_prompt = "\n".join(
        [
            f"REQUEST (cleaned): {(request_text or '').strip()}",
            f"RAW REQUEST: {(task.raw_text or '').strip()[:4000]}",
            f"REQUESTER: {requester_label}",
            f"ASSIGNEE HINT: {assignee_hint}",
            f"MENTION MAP (U id → display name): {json.dumps(labels, ensure_ascii=False)}",
            f"THREAD URL: {thread_url or '(none)'}",
            "",
            f"Produce exactly {len(fallbacks)} tasks, one per SOURCE ITEM, same order.",
            "Each description is for THAT item only — never paste the full list into every ticket.",
            "",
            "SOURCE ITEMS:",
            numbered,
            "",
            "THREAD MESSAGES:",
            (messages_text or "").strip()[:8000] or "(none)",
        ]
    )

    try:
        response = provider.chat(
            [
                Message(role="system", content=BOARD_TASK_BATCH_DRAFT_SYSTEM),
                Message(role="user", content=user_prompt),
            ],
            model=model or None,
        )
    except Exception as exc:
        logger.warning("Board batch draft LLM call failed: %s", exc)
        return fallbacks

    rows = _parse_batch_task_rows(response.content or "")
    if not rows:
        return fallbacks

    drafts: list[BoardTaskDraft] = []
    used: set[int] = set()
    for fallback in fallbacks:
        row: dict[str, Any] | None = None
        source_key = fallback.title.strip().lower()
        for idx, candidate in enumerate(rows):
            if idx in used:
                continue
            source_title = str(candidate.get("source_title") or "").strip().lower()
            if source_title and source_title == source_key:
                row = candidate
                used.add(idx)
                break
        if row is None:
            for idx, candidate in enumerate(rows):
                if idx not in used:
                    row = candidate
                    used.add(idx)
                    break
        if row is None:
            drafts.append(fallback)
            continue

        description = str(row.get("description") or "").strip()
        if not description:
            description = fallback.description
        description = humanize_board_task_text(description, labels)
        title = _resolve_draft_title(
            str(row.get("title") or ""),
            description,
            hint_title=fallback.title,
            request_text=request_text,
        ) or fallback.title
        assignee = str(row.get("assignee_user_id") or "").strip()
        if assignee and not re.fullmatch(r"U[A-Z0-9]+", assignee):
            assignee = ""
        severity = normalize_board_severity(str(row.get("severity") or "")) or fallback.severity
        drafts.append(
            BoardTaskDraft(
                title=title[:200],
                description=description[:4000],
                assignee_user_id=assignee or fallback.assignee_user_id,
                severity=severity,
            )
        )
    return drafts
