"""Mandatory thread fetch + task create before Slack board agent loop."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from backend.ai.base import Message
from backend.integrations.slack.board_service import (
    board_enabled,
    create_board_task,
    resolve_board_for_task,
)
from backend.integrations.slack.context import fetch_thread_messages, messages_to_text
from backend.routing.slack_board_intent import (
    build_thread_description,
    extract_task_title,
)

logger = logging.getLogger(__name__)


def bootstrap_slack_board_create(
    client: Any,
    config: Any,
    *,
    task: Any,
    data_dir: Path | None,
    title_override: str = "",
) -> str:
    """Fetch thread context and create a list item. Returns context for the agent."""
    if not board_enabled(config, data_dir):
        return "Slack board workflows are disabled in config."

    board = resolve_board_for_task(config, task, data_dir=data_dir)
    if board is None:
        return "No Slack board configured for this channel — link a List in Settings → Slack boards."

    from backend.db.slack_board_store import SlackBoardStore

    store = SlackBoardStore(data_dir) if data_dir else SlackBoardStore(Path(".alfred"))

    title = (title_override or extract_task_title(task.cleaned_intent or task.raw_text or "")).strip()
    if not title:
        title = (task.cleaned_intent or task.raw_text or "Slack thread task")[:120].strip()

    description = ""
    in_thread = bool(task.channel_id and task.thread_ts)
    if in_thread:
        try:
            messages = fetch_thread_messages(
                client,
                task,
                limit=50,
                bot_user_id=_bot_user_id(client),
            )
            description = build_thread_description(messages_to_text(messages))
        except Exception as exc:
            logger.warning("Thread fetch for board create failed: %s", exc)
            description = f"Thread context unavailable: {exc}"

    if not description.strip():
        description = "Created from Slack conversation."

    try:
        result = create_board_task(
            client,
            config,
            store,
            board,
            title=title,
            description=description,
            channel_id=task.channel_id or "",
            thread_ts=task.thread_ts or "",
        )
    except Exception as exc:
        logger.exception("Slack board create failed")
        return f"Failed to create board task: {exc}"

    lines = [
        "## Slack board task (already created — confirm to the user)",
        f"Title: {result.get('title')}",
        f"Display id: {result.get('display_id') or '(none)'}",
        f"Record id: {result.get('record_id')}",
        f"Board: {result.get('board')}",
        f"Status: {result.get('status')}",
        "",
        "### Thread summary used",
        description[:4000],
        "",
        "### tool result",
        json.dumps(result, indent=2),
    ]
    return "\n".join(lines)


def inject_slack_board_bootstrap_message(
    messages: list[Message],
    client: Any,
    config: Any,
    *,
    task: Any,
    data_dir: Path | None,
) -> list[Message]:
    bootstrap = bootstrap_slack_board_create(
        client,
        config,
        task=task,
        data_dir=data_dir,
    )
    out = list(messages)
    out.append(
        Message(
            role="user",
            content=(
                f"{bootstrap}\n\n"
                "Using ONLY the result above, confirm the task was created. "
                "Include the display id (if any), record id, title, and status. "
                "Do not claim success if the bootstrap reports failure."
            ),
        )
    )
    return out


def _bot_user_id(client: Any) -> str:
    try:
        auth = client.auth_test()
        return str(auth.get("user_id") or "")
    except Exception:
        return ""
