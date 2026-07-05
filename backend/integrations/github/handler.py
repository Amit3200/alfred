"""Process GitHub webhook events and post replies."""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from backend.config_manager import ConfigManager
from backend.integrations.github.client import (
    REACTION_ACK,
    REACTION_DONE,
    REACTION_FAILED,
    post_pull_request_comment,
    react_to_issue_comment,
)
from backend.integrations.github.sanitize import task_from_issue_comment
from backend.orchestrator.processor import TaskProcessor
from backend.formatting.render import render_for_channel
from backend.models.config import AlfredConfig
from backend.models.task import Task

logger = logging.getLogger(__name__)


def process_github_webhook_payload(
    payload: dict[str, Any],
    *,
    manager: ConfigManager,
    processor_factory: Callable[[], TaskProcessor] | None = None,
) -> str:
    """Handle a verified GitHub webhook JSON body. Returns a short status string."""
    event = str(payload.get("_github_event") or "")
    if event == "ping":
        return "pong"

    config, _ = manager.load_merged()
    if not config.github.enabled:
        return "github ingress disabled"

    if event != "issue_comment":
        return f"ignored event {event}"

    task = task_from_issue_comment(payload, config=config)
    if task is None:
        return "ignored issue_comment"

    _react_ack(config, task, REACTION_ACK)

    from backend.db.sqlite_queue import SQLiteQueue
    queue = SQLiteQueue(manager.data_dir)
    queue.push(task.model_dump())
    return "queued"


def _comment_id(task: Task) -> int | None:
    raw = task.metadata.get("comment_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _react_ack(config: AlfredConfig, task: Task, content: str) -> None:
    comment_id = _comment_id(task)
    if not comment_id:
        return
    try:
        react_to_issue_comment(
            config,
            repo=task.channel_id,
            comment_id=comment_id,
            content=content,
        )
        logger.info(
            "GitHub comment reaction %s repo=%s comment=%s",
            content,
            task.channel_id,
            comment_id,
        )
    except Exception:
        logger.exception(
            "Failed to react %s on GitHub comment repo=%s comment=%s",
            content,
            task.channel_id,
            comment_id,
        )
