"""Direct Slack board create/status — no agent loop required."""

from __future__ import annotations

import logging
import re
from typing import Any

from backend.integrations.slack.board_service import board_enabled, create_board_task, resolve_board_for_task
from backend.integrations.slack.sanitize import extract_slack_user_ids
from backend.models.config import AlfredConfig
from backend.models.response import AssistantResponse
from backend.models.task import Task
from backend.routing.slack_board_intent import (
    build_thread_description,
    extract_task_title,
    looks_like_slack_board_create,
    looks_like_slack_board_followup,
    references_thread_context,
)

logger = logging.getLogger(__name__)

_SEVERITY_RE = re.compile(r"\b(p0|p1|p2|p3)\b", re.I)
_TICKET_REF_IN_TEXT_RE = re.compile(r"\b((?:TS|BUG|TK|T)-\d+|Rec[A-Za-z0-9]+)\b", re.I)


def extract_board_create_fields(task: Task) -> dict[str, str]:
    """Parse title, severity, and assignee from a create-task message."""
    intent = task.cleaned_intent or task.raw_text or ""
    title = extract_task_title(intent).strip()
    if not title:
        title = extract_task_title(task.raw_text or "").strip()
    severity = ""
    sev_match = _SEVERITY_RE.search(intent)
    if sev_match:
        severity = sev_match.group(1).upper()
        title = _SEVERITY_RE.sub("", title).strip(" .,:;-")
        title = re.sub(r"\s+as\s*$", "", title, flags=re.I).strip()
    title = re.sub(
        r"\s+and\s+assign\b.*$",
        "",
        title,
        flags=re.I,
    ).strip(" .,:;-")
    assignee_user_id = ""
    user_ids = extract_slack_user_ids(task.raw_text or intent)
    if user_ids:
        assignee_user_id = user_ids[-1]
    return {
        "title": title[:200],
        "severity": severity,
        "assignee_user_id": assignee_user_id,
    }


def format_board_task_created(result: dict[str, Any], *, severity: str = "", assignee_user_id: str = "") -> str:
    display_id = result.get("display_id") or ""
    title = result.get("title") or "Task"
    status = result.get("status") or "Not picked"
    lines = [
        f"Created board task **{display_id or result.get('record_id')}** — *{title}*",
        f"- Status: `{status}`",
    ]
    if severity:
        lines.append(f"- Severity: `{severity}`")
    if assignee_user_id:
        lines.append(f"- Assignee: `<@{assignee_user_id}>`")
    lines.append(f"- Record: `{result.get('record_id')}`")
    return "\n".join(lines)


def try_slack_board_create_direct(
    task: Task,
    config: AlfredConfig,
    data_dir: Any,
) -> tuple[AssistantResponse | None, dict[str, Any]]:
    """Create a list task immediately when the user asks (Slack only)."""
    if task.source != "slack" or not config.slack.enabled:
        return None, {}
    if not looks_like_slack_board_create(task.cleaned_intent or ""):
        return None, {}

    if not board_enabled(config, data_dir):
        return (
            AssistantResponse.from_text(
                "Slack List boards are not configured yet. "
                "Say `@alfred link board to F…` or use **Settings → Slack boards**."
            ),
            {},
        )

    board = resolve_board_for_task(config, task, data_dir=data_dir)
    if board is None:
        return (
            AssistantResponse.from_text(
                "This channel is not linked to a Slack List yet. "
                "Say `@alfred link board to F0123…` (List id from the Task List tab)."
            ),
            {},
        )

    fields = extract_board_create_fields(task)
    title = fields["title"]
    if not title and references_thread_context(task.cleaned_intent or ""):
        title = (task.cleaned_intent or "Slack thread task")[:120].strip()
    if not title:
        return (
            AssistantResponse.from_text(
                "What should the task be called? Example: "
                "`@alfred create task for payment timeout on checkout`"
            ),
            {},
        )

    token = (config.slack.bot_token or "").strip()
    if not token:
        return AssistantResponse.error("Slack bot token is not configured."), {}

    from slack_sdk import WebClient

    from backend.db.slack_board_store import SlackBoardStore
    from backend.integrations.slack.context import fetch_thread_messages, messages_to_text
    from backend.routing.slack_board_bootstrap import _bot_user_id

    client = WebClient(token=token)
    store = SlackBoardStore(data_dir) if data_dir else SlackBoardStore(None)

    description = "Created from Slack conversation."
    if task.channel_id and task.thread_ts:
        try:
            messages = fetch_thread_messages(
                client,
                task,
                limit=50,
                bot_user_id=_bot_user_id(client),
            )
            if messages:
                description = build_thread_description(messages_to_text(messages))
        except Exception as exc:
            logger.warning("Thread fetch for direct board create failed: %s", exc)

    try:
        result = create_board_task(
            client,
            config,
            store,
            board,
            title=title,
            description=description,
            severity=fields["severity"],
            assignee_user_id=fields["assignee_user_id"],
            channel_id=task.channel_id or "",
            thread_ts=task.thread_ts or "",
        )
    except Exception as exc:
        logger.exception("Direct Slack board create failed")
        return AssistantResponse.error(f"Could not create board task: {exc}"), {}

    body = format_board_task_created(
        result,
        severity=fields["severity"],
        assignee_user_id=fields["assignee_user_id"],
    )
    metadata = {
        "last_board_task": {
            "display_id": result.get("display_id"),
            "record_id": result.get("record_id"),
            "title": result.get("title"),
            "status": result.get("status"),
            "board": result.get("board"),
        }
    }
    return AssistantResponse.from_text(body), metadata


def try_slack_board_status_followup(
    task: Task,
    config: AlfredConfig,
    data_dir: Any,
    *,
    session: Any | None = None,
    session_turns: tuple[str, ...] = (),
    thread_context: str | None = None,
) -> AssistantResponse | None:
    """Answer 'is it created?' style follow-ups from session state."""
    if task.source != "slack" or not config.slack.enabled:
        return None
    if not looks_like_slack_board_followup(
        task.cleaned_intent or "",
        session_turns=session_turns,
        thread_context=thread_context,
    ):
        return None

    last = {}
    if session is not None:
        last = dict((session.metadata or {}).get("last_board_task") or {})

    if not last:
        combined = "\n".join([*session_turns[-6:]])
        ref = _TICKET_REF_IN_TEXT_RE.search(combined)
        if ref:
            last = {"display_id": ref.group(1)}

    if last.get("display_id") or last.get("record_id"):
        display = last.get("display_id") or last.get("record_id")
        title = last.get("title") or "Task"
        status = last.get("status") or "Not picked"
        return AssistantResponse.from_text(
            f"Yes — **{display}** is on the board: *{title}* (status `{status}`)."
        )

    return AssistantResponse.from_text(
        "I don't see a task created in this thread yet. "
        "Ask `@alfred create task for …` and I'll create it on the linked List immediately."
    )
