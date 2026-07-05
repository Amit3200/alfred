"""Asynchronous queue worker to execute Tasks in the background."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

from backend.config_manager import ConfigManager
from backend.db.sqlite_queue import SQLiteQueue
from backend.db.session_store import SessionStore
from backend.formatting.render import render_for_channel
from backend.models.task import Task
from backend.observability.checkpoint import current_data_dir, current_task_id, log_checkpoint
from backend.orchestrator.processor import TaskProcessor

logger = logging.getLogger(__name__)


class TaskQueueWorker:
    def __init__(self, manager: ConfigManager, queue: SQLiteQueue) -> None:
        self.manager = manager
        self.queue = queue
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="alfred-queue-worker",
            daemon=True,
        )
        self._thread.start()
        logger.info("Task queue worker thread started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        self._thread = None
        logger.info("Task queue worker thread stopped")

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                task_dict = self.queue.pop()
                if not task_dict:
                    time.sleep(0.5)
                    continue

                task_id = task_dict.get("id")
                # Bind context variables for this task execution
                token_task_id = current_task_id.set(task_id)
                token_data_dir = current_data_dir.set(self.manager.data_dir)

                logger.info("Dequeued task %s for processing", task_id)
                log_checkpoint("queue_task", task_id, "started")

                try:
                    task = Task.model_validate(task_dict)
                    config, _ = self.manager.load_merged()
                    store = SessionStore(self.manager.data_dir)

                    # Inline imports to avoid circular dependency rings
                    context_fetcher = None
                    if task.source == "slack":
                        from backend.integrations.slack.context import fetch_slack_context
                        from backend.integrations.slack.emojis import slack_bot_client

                        client = slack_bot_client(config.slack.bot_token)
                        bot_user_id = client.auth_test().get("user_id", "")
                        context_fetcher = lambda t: fetch_slack_context(
                            client, t, bot_user_id=bot_user_id
                        )

                    processor = TaskProcessor(
                        config,
                        session_store=store,
                        data_dir=self.manager.data_dir,
                        context_fetcher=context_fetcher,
                    )

                    response = processor.process(task)

                    if config.orchestrator.self_improvement and response.text:
                        from backend.orchestrator.learning import analyze_and_generate_playbook
                        analyze_and_generate_playbook(
                            task,
                            response.text,
                            config,
                            data_dir=self.manager.data_dir
                        )

                    if task.source == "slack":
                        from backend.formatting.file_exports import prepare_slack_delivery
                        from backend.integrations.slack.users import (
                            SlackUserResolver,
                            resolve_user_ids_in_text,
                        )
                        from backend.integrations.slack.emojis import slack_bot_client

                        client = slack_bot_client(config.slack.bot_token)
                        rendered = render_for_channel(response, "slack")
                        resolver = SlackUserResolver(client)
                        rendered = resolve_user_ids_in_text(rendered, resolver)
                        delivery = prepare_slack_delivery(rendered, task.cleaned_intent)

                        # Post text response
                        client.chat_postMessage(
                            channel=task.channel_id,
                            thread_ts=task.thread_ts,
                            text=delivery.text,
                        )

                        # Post files
                        for file in delivery.files:
                            client.files_upload_v2(
                                channel=task.channel_id,
                                thread_ts=task.thread_ts,
                                title=file.title,
                                filename=file.filename,
                                content=file.content,
                            )
                    elif task.source == "ui":
                        # For UI Chat, processor.process(task) automatically appends the exchange to SessionStore
                        pass
                    elif task.source == "github":
                        from backend.formatting.render import render_for_channel
                        from backend.integrations.github.client import post_pull_request_comment, REACTION_DONE
                        from backend.integrations.github.handler import _react_ack

                        body = render_for_channel(response, "github")
                        number = int(task.metadata.get("pr_number") or task.thread_ts or 0)
                        post_pull_request_comment(
                            config,
                            repo=task.channel_id,
                            number=number,
                            body=body,
                        )
                        _react_ack(config, task, REACTION_DONE)

                    self.queue.ack(task_id)
                    log_checkpoint("queue_task", task_id, "completed")

                except Exception as exc:
                    logger.exception("Error processing dequeued task %s", task_id)
                    self.queue.fail(task_id)
                    log_checkpoint("queue_task", task_id, "error", error=exc)

                    # Post failure back to source channel if possible
                    if task_dict.get("source") == "slack" and task_dict.get("channel_id"):
                        try:
                            from backend.integrations.slack.emojis import slack_bot_client

                            client = slack_bot_client(config.slack.bot_token)
                            client.chat_postMessage(
                                channel=task_dict["channel_id"],
                                thread_ts=task_dict.get("thread_ts"),
                                text=f"Sorry, I hit an error: {exc}",
                            )
                        except Exception:
                            logger.exception("Failed to send error details back to Slack")
                    elif task_dict.get("source") == "github" and task_dict.get("channel_id"):
                        try:
                            from backend.integrations.github.client import post_pull_request_comment, REACTION_FAILED
                            from backend.integrations.github.handler import _react_ack
                            task_to_err = Task.model_validate(task_dict)
                            number = int(task_to_err.metadata.get("pr_number") or task_to_err.thread_ts or 0)
                            post_pull_request_comment(
                                config,
                                repo=task_to_err.channel_id,
                                number=number,
                                body=(
                                    "Sorry, I hit an error processing that request. "
                                    "Check Alfred logs and that git integration + investigation routing are configured."
                                ),
                            )
                            _react_ack(config, task_to_err, REACTION_FAILED)
                        except Exception:
                            logger.exception("Failed to post GitHub error comment")
                finally:
                    # Reset request context variables
                    current_task_id.reset(token_task_id)
                    current_data_dir.reset(token_data_dir)

            except Exception:
                logger.exception("Worker thread main execution loop error")
                time.sleep(1.0)
