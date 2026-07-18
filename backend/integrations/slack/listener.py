"""Slack Socket Mode listener for @alfred mentions."""

from __future__ import annotations
from slack_bolt import App
from backend.integrations.slack.users import SlackUserResolver, resolve_user_ids_in_text
from backend.db.slack_user_cache import SlackUserCache
from slack_bolt.adapter.socket_mode import SocketModeHandler


import logging
import threading
from typing import Any, Callable

from backend.config_manager import ConfigManager
from backend.formatting.file_exports import prepare_slack_delivery
from backend.formatting.render import render_for_channel
from backend.integrations.slack.context import fetch_slack_context
from backend.integrations.slack.sanitize import sanitize_slack_mention
from backend.models.config import AlfredConfig
from backend.db.session_store import SessionStore

from backend.integrations.slack.status import ThinkingIndicator

logger = logging.getLogger(__name__)


def slack_listener_ready(config: AlfredConfig) -> tuple[bool, str]:
    if not config.slack.enabled:
        return False, "Slack disabled in Integrations"
    bot = (config.slack.bot_token or "").strip()
    app = (config.slack.app_token or "").strip()
    signing = (config.slack.signing_secret or "").strip()
    if not bot.startswith("xoxb-"):
        return False, "Slack bot token (xoxb-) not configured"
    if not app.startswith("xapp-"):
        return False, "Slack app token (xapp-) required for Socket Mode"
    if not signing:
        return False, "Slack signing secret not configured"
    return True, "Ready"


def build_slack_bolt_app(
    config: AlfredConfig,
    *,
    data_dir: Any = None,
    on_task_complete: Callable[[], None] | None = None,
    queue: Any | None = None,
) -> Any:
    pass

    app = App(token=config.slack.bot_token, signing_secret=config.slack.signing_secret)
    auth = app.client.auth_test()
    bot_user_id = auth.get("user_id", "")
    session_store = SessionStore(data_dir) if data_dir else None

    from backend.orchestrator.processor import TaskProcessor
    processor = TaskProcessor(
        config,
        session_store=session_store,
        data_dir=data_dir,
        context_fetcher=lambda task: fetch_slack_context(
            app.client,
            task,
            bot_user_id=bot_user_id,
            thread_relevance_enabled=config.slack.thread_relevance_enabled,
            thread_relevance_top_n=config.slack.thread_relevance_top_n,
            thread_fetch_limit=config.slack.thread_fetch_limit,
        ),
    )

    @app.event("app_mention")
    def handle_app_mention(event: dict, client: Any, logger: Any) -> None:  # noqa: ARG001
        task = sanitize_slack_mention(event, config.slack)
        if task is None:
            logger.debug("Ignored app_mention (channel not allowed or empty text)")
            return

        channel = event.get("channel") or task.channel_id
        thread_ts = task.thread_ts
        logger.info(
            "app_mention user=%s channel=%s thread=%s intent=%r",
            task.user_id,
            channel,
            thread_ts,
            task.cleaned_intent[:120],
        )

        if queue is not None:
            # Enqueue the task for async processing
            task_dict = task.model_dump()
            queue.push(task_dict)
        else:
            # Fallback to direct thread processing (backward compatibility / standalone tests)
            indicator = ThinkingIndicator(
                client,
                channel=channel,
                thread_ts=thread_ts,
                loading_messages=config.slack.loading_messages or None,
            )
            indicator.start()

            worker = threading.Thread(
                target=_process_mention,
                args=(task, processor, indicator, app.client, on_task_complete),
                daemon=True,
                name=f"alfred-slack-{task.id[:8]}",
            )
            worker.start()

    @app.action("feedback_good")
    def handle_feedback_good(ack: Any, body: dict, respond: Any) -> None:
        ack()
        task_id = body.get("actions", [{}])[0].get("value")
        if task_id and data_dir:
            from pathlib import Path
            from backend.observability.checkpoint import save_task_feedback
            save_task_feedback(Path(data_dir), task_id, "good")
        respond("Thank you for your feedback! (Good 👍)")

    @app.action("feedback_bad")
    def handle_feedback_bad(ack: Any, body: dict, respond: Any) -> None:
        ack()
        task_id = body.get("actions", [{}])[0].get("value")
        if task_id and data_dir:
            from pathlib import Path
            from backend.observability.checkpoint import save_task_feedback
            save_task_feedback(Path(data_dir), task_id, "bad")
        respond("Thank you for your feedback! (Bad 👎)")

    return app


def _process_mention(
    task: Any,
    processor: TaskProcessor,
    indicator: ThinkingIndicator,
    client: Any,
    on_task_complete: Callable[[], None] | None,
) -> None:
    try:
        pass
        pass

        display_name = SlackUserResolver(client).display_name(task.user_id)
        task.metadata["user_label"] = display_name
        if processor._data_dir is not None:
            SlackUserCache(processor._data_dir).remember(task.user_id, display_name)
        response = processor.process(task)
        rendered = render_for_channel(response, "slack")
        resolver = SlackUserResolver(client)
        rendered = resolve_user_ids_in_text(rendered, resolver)
        delivery = prepare_slack_delivery(
            rendered,
            task.cleaned_intent,
        )
        indicator.finish(delivery.text, files=delivery.files)

        # Randomly ask for feedback (1 out of 20 = 5% chance)
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
                logger.exception("Failed to send Slack feedback poll in direct processing")
    except Exception as exc:
        logger.exception("Failed to process Slack mention %s", task.id)
        indicator.finish(f"Sorry, I hit an error: {exc}")
    finally:
        if on_task_complete:
            on_task_complete()


class SlackSocketRunner:
    """Runs Slack Bolt Socket Mode in a background thread."""

    def __init__(self, manager: ConfigManager) -> None:
        self.manager = manager
        self._handler: Any | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.last_error: str | None = None
        self.running = False

    def start(self) -> tuple[bool, str]:
        config, _ = self.manager.load_merged()
        ready, message = slack_listener_ready(config)
        if not ready:
            self.last_error = message
            return False, message
        if self.running:
            return True, "Already listening"

        try:
            pass

            from backend.db.sqlite_queue import SQLiteQueue
            queue = SQLiteQueue(self.manager.data_dir)
            bolt_app = build_slack_bolt_app(config, data_dir=self.manager.data_dir, queue=queue)
            self._handler = SocketModeHandler(bolt_app, config.slack.app_token)
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="alfred-slack-socket",
                daemon=True,
            )
            self._thread.start()
            self.running = True
            self.last_error = None
            logger.info("Slack Socket Mode listener started")
            return True, "Listening for @mentions via Socket Mode"
        except ImportError:
            message = "slack-bolt not installed — run: pip install 'alfred-agent[slack]'"
            self.last_error = message
            return False, message
        except Exception as exc:
            message = str(exc)
            self.last_error = message
            logger.exception("Failed to start Slack listener")
            return False, message

    def _run_loop(self) -> None:
        try:
            assert self._handler is not None
            self._handler.connect()
        except Exception as exc:
            self.last_error = str(exc)
            logger.exception("Slack Socket Mode listener stopped")
        finally:
            self.running = False

    def stop(self) -> None:
        self._stop_event.set()
        handler = self._handler
        self._handler = None
        if handler is not None:
            try:
                handler.close()
            except Exception:
                logger.debug("Error closing Slack handler", exc_info=True)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        self.running = False

    def restart(self) -> tuple[bool, str]:
        """Stop and start the listener (picks up fresh tokens/config)."""
        logger.info("Restarting Slack Socket Mode listener")
        self.stop()
        ok, message = self.start()
        if ok:
            logger.info("Slack listener restarted: %s", message)
        else:
            logger.warning("Slack listener restart skipped/failed: %s", message)
        return ok, message

    def status(self) -> dict:
        config, _ = self.manager.load_merged()
        if not config.slack.enabled:
            return {"ok": False, "skipped": True, "message": "Slack disabled in Integrations"}
        ready, ready_message = slack_listener_ready(config)
        if self.running:
            return {
                "ok": True,
                "message": "Listening for @mentions (Socket Mode)",
                "running": True,
            }
        if self.last_error:
            return {"ok": False, "message": self.last_error, "running": False}
        if not ready:
            return {"ok": False, "message": ready_message, "running": False}
        return {
            "ok": False,
            "message": "Configured but listener not running — restart alfred serve",
            "running": False,
        }
