"""Ensure JIRA creates always carry a useful description plus Slack thread link."""

from __future__ import annotations

from typing import Any

from backend.domains.slack_board.formatting import slack_thread_permalink
from backend.models.task import Task


def enrich_jira_create_description(
    description: str,
    *,
    summary: str = "",
    task: Task | None = None,
    session_metadata: dict[str, Any] | None = None,
    channel_id: str = "",
    thread_ts: str = "",
    team_id: str = "",
) -> str:
    """Keep LLM text, fill a fallback, and always attach the Slack thread URL when known."""
    body = (description or "").strip()
    from backend.domains.jira.thread_fields import is_placeholder_jira_text

    if is_placeholder_jira_text(body):
        body = ""
    channel = (channel_id or (task.channel_id if task else "") or "").strip()
    ts = (thread_ts or (str(task.thread_ts or "") if task else "") or "").strip()
    permalink = slack_thread_permalink(channel_id=channel, thread_ts=ts, team_id=team_id)
    last = dict((session_metadata or {}).get("last_board_task") or {})
    intent = (task.cleaned_intent if task else "") or (task.raw_text if task else "") or ""

    parts: list[str] = []
    if body:
        parts.append(body)
    else:
        title = (summary or "").strip() or (str(last.get("title") or "")).strip()
        if title:
            parts.append(title)
        if intent and intent.strip() not in {title, body}:
            parts.append(f"Requested in Slack: {intent.strip()}")
        if not parts:
            parts.append("Created from Slack.")

    board_line = _board_line(last)
    blob = "\n".join(parts)
    if board_line and board_line not in blob and str(last.get("display_id") or "") not in blob:
        parts.append(board_line)
        blob = "\n".join(parts)
    if permalink and permalink not in blob:
        parts.append(f"Slack thread: {permalink}")
    return "\n\n".join(part for part in parts if part).strip()


def _board_line(last: dict[str, Any]) -> str:
    display = str(last.get("display_id") or "").strip()
    record = str(last.get("record_id") or "").strip()
    list_name = str(last.get("list_name") or last.get("board") or "").strip()
    open_url = str(last.get("open_url") or "").strip()
    if not display and not record:
        return ""
    label = display or record
    bits = [f"Slack List: {label}"]
    if list_name:
        bits.append(f"({list_name})")
    if record and record != display:
        bits.append(f"record {record}")
    line = " ".join(bits)
    if open_url:
        return f"{line}\n{open_url}"
    return line
