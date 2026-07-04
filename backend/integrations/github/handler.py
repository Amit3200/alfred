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

    worker = threading.Thread(
        target=_process_github_task,
        args=(task, manager, processor_factory),
        daemon=True,
        name=f"alfred-github-{task.id[:8]}",
    )
    worker.start()
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


def _process_github_task(
    task: Task,
    manager: ConfigManager,
    processor_factory: Callable[[], TaskProcessor] | None,
) -> None:
    config, _ = manager.load_merged()
    success = False
    try:
        processor = processor_factory() if processor_factory else TaskProcessor(config, data_dir=manager.data_dir)
        response = processor.process(task)
        body = render_for_channel(response, "github")
        number = int(task.metadata.get("pr_number") or task.thread_ts or 0)
        post_pull_request_comment(
            config,
            repo=task.channel_id,
            number=number,
            body=body,
        )
        logger.info(
            "GitHub PR comment posted repo=%s pr=%s task=%s",
            task.channel_id,
            number,
            task.id,
        )
        success = True
    except Exception:
        logger.exception("Failed to process GitHub task %s", task.id)
        try:
            number = int(task.metadata.get("pr_number") or task.thread_ts or 0)
            post_pull_request_comment(
                config,
                repo=task.channel_id,
                number=number,
                body=(
                    "Sorry, I hit an error processing that request. "
                    "Check Alfred logs and that git integration + investigation routing are configured."
                ),
            )
        except Exception:
            logger.exception("Failed to post GitHub error comment for task %s", task.id)
    finally:
        _react_ack(config, task, REACTION_DONE if success else REACTION_FAILED)
