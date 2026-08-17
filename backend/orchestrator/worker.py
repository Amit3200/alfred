"""Asynchronous queue worker to execute Tasks in the background."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

from backend.config_manager import ConfigManager
from backend.routing.playbook_store_registry import get_playbook_store
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
                    indicator = None
                    if task.source == "slack":
                        from backend.integrations.slack.context import fetch_slack_context
                        from backend.integrations.slack.emojis import slack_bot_client
                        from backend.integrations.slack.status import ThinkingIndicator

                        client = slack_bot_client(config.slack.bot_token)
                        bot_user_id = client.auth_test().get("user_id", "")
                        context_fetcher = lambda t: fetch_slack_context(
                            client,
                            t,
                            bot_user_id=bot_user_id,
                            thread_relevance_enabled=config.slack.thread_relevance_enabled,
                            thread_relevance_top_n=config.slack.thread_relevance_top_n,
                            thread_fetch_limit=config.slack.thread_fetch_limit,
                        )

                        indicator = ThinkingIndicator(
                            client,
                            channel=task.channel_id,
                            thread_ts=task.thread_ts,
                            loading_messages=config.slack.loading_messages or None,
                        )
                        indicator.start()

                    processor = TaskProcessor(
                        config,
                        session_store=store,
                        data_dir=self.manager.data_dir,
                        context_fetcher=context_fetcher,
                        playbook_store=get_playbook_store(
                            self.manager.data_dir,
                            disabled_skills=config.skills.disabled,
                        ),
                    )

                    response = processor.process(task)

                    if config.orchestrator.self_improvement and response.text and not self.queue.is_cancelled(task_id):
                        from backend.orchestrator.learning import analyze_and_generate_playbook
                        analyze_and_generate_playbook(
                            task,
                            response.text,
                            config,
                            data_dir=self.manager.data_dir
                        )

                    if task.source == "slack" or (task.source == "scheduler" and task.channel_id):
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
                        from backend.routing.ticket_create_disambiguation import slack_blocks_from_response

                        blocks = slack_blocks_from_response(response) or delivery.blocks

                        if task.source == "slack" and indicator is not None:
                            indicator.finish(delivery.text, files=delivery.files, blocks=blocks)
                        else:
                            client.chat_postMessage(
                                channel=task.channel_id,
                                thread_ts=task.thread_ts,
                                text=delivery.text,
                            )

                        # Randomly ask for feedback (1 out of 20 = 5% chance)
                        if task.source == "slack":
                            import random
                            if random.random() < 0.05:
                                try:
                                    client.chat_postMessage(
                                        channel=task.channel_id,
                                        thread_ts=task.thread_ts,
                                        text="Did Alfred do good or bad?",
                                        blocks=[
                                            {
                                                "type": "section",
                                                "text": {
                                                    "type": "mrkdwn",
                                                    "text": "Did Alfred do good or bad?"
                                                }
                                            },
                                            {
                                                "type": "actions",
                                                "elements": [
                                                    {
                                                        "type": "button",
                                                        "text": {
                                                            "type": "plain_text",
                                                            "text": "Good 👍",
                                                            "emoji": True
                                                        },
                                                        "value": task.id,
                                                        "action_id": "feedback_good"
                                                    },
                                                    {
                                                        "type": "button",
                                                        "text": {
                                                            "type": "plain_text",
                                                            "text": "Bad 👎",
                                                            "emoji": True
                                                        },
                                                        "value": task.id,
                                                        "action_id": "feedback_bad"
                                                    }
                                                ]
                                            }
                                        ]
                                    )
                                except Exception:
                                    logger.exception("Failed to send Slack feedback poll")

                    if task.source == "scheduler":
                        job_id = task.metadata.get("job_id")
                        if job_id:
                            try:
                                from backend.db.sqlite_schedule import db_update_last_run
                                db_update_last_run(self.manager.data_dir, job_id, "success")
                            except Exception:
                                logger.exception("Failed to update last run status to success for job %s", job_id)

                    elif task.source == "ui":
                        # processor.process(task) appends the assistant reply on success
                        pass
                    elif task.source == "github":
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

                    if self.queue.is_cancelled(task_id):
                        log_checkpoint("queue_task", task_id, "cancelled")
                    else:
                        self.queue.ack(task_id)
                        log_checkpoint("queue_task", task_id, "completed")

                    # If the task was triggered from Slack/UI and contains a PR review, mirror comments directly to GitHub
                    if task.source != "github" and config.git.enabled and config.git.token and response.text:
                        from backend.models.session import task_session_key
                        session_key = task_session_key(task)
                        session = store.load(session_key) if (session_key and store) else None
                        active_pr = (session.metadata or {}).get("active_pr") if session else None
                        
                        is_pr_review = (
                            "review" in task.cleaned_intent.lower() 
                            or "pr" in task.cleaned_intent.lower()
                        )
                        if active_pr and is_pr_review:
                            try:
                                from backend.integrations.github.client import post_pull_request_comment
                                body = render_for_channel(response, "github")
                                post_pull_request_comment(
                                    config,
                                    repo=active_pr["repo"],
                                    number=int(active_pr["number"]),
                                    body=body,
                                )
                                logger.info("Mirrored review comments to GitHub PR #%s", active_pr["number"])
                            except Exception as git_exc:
                                logger.warning("Failed to auto-mirror review comments to GitHub: %s", git_exc)

                except Exception as exc:
                    logger.exception("Error processing dequeued task %s", task_id)
                    self.queue.fail(task_id)
                    log_checkpoint("queue_task", task_id, "error", error=exc)
                    if task_dict.get("source") == "scheduler":
                        job_id = task_dict.get("metadata", {}).get("job_id")
                        if job_id:
                            try:
                                from backend.db.sqlite_schedule import db_update_last_run
                                db_update_last_run(self.manager.data_dir, job_id, "failed")
                            except Exception:
                                pass

                    # Post failure back to source channel if possible
                    if task_dict.get("source") in ("slack", "scheduler") and task_dict.get("channel_id"):
                        try:
                            from backend.integrations.slack.emojis import slack_bot_client

                            client = slack_bot_client(config.slack.bot_token)
                            if task_dict.get("source") == "slack" and indicator is not None:
                                indicator.finish(f"Sorry, I hit an error: {exc}")
                            else:
                                client.chat_postMessage(
                                    channel=task_dict["channel_id"],
                                    thread_ts=task_dict.get("thread_ts"),
                                    text=f"Sorry, I hit an error: {exc}",
                                )
                        except Exception:
                            logger.exception("Failed to send error details back to Slack")
                    elif task_dict.get("source") == "ui" and task_dict.get("channel_id"):
                        try:
                            from backend.api.ui_chat import UI_SOURCE, ui_session_key
                            from backend.models.response import ResponsePayload

                            chat_id = str(task_dict["channel_id"])
                            store = SessionStore(self.manager.data_dir)
                            store.append_assistant_turn(
                                ui_session_key(chat_id),
                                source=UI_SOURCE,
                                scope_id=chat_id,
                                thread_id=chat_id,
                                assistant_content=(
                                    f"Sorry, I hit an error while processing your request: {exc}"
                                ),
                                assistant_payload=ResponsePayload(
                                    kind="error",
                                    data={"message": str(exc)},
                                ),
                            )
                        except Exception:
                            logger.exception("Failed to append UI chat error reply")
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
