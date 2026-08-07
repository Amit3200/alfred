"""Slack interactive handlers for JIRA vs Slack List disambiguation."""

from __future__ import annotations

import logging
import threading
from typing import Any

from backend.db.session_store import SessionStore
from backend.models.task import Task
from backend.routing.ticket_create_disambiguation import (
    TicketCreateTarget,
    decode_button_session_value,
    task_from_pending_session,
)

logger = logging.getLogger(__name__)


def register_ticket_disambiguation_actions(
    app: Any,
    *,
    processor: Any,
    session_store: SessionStore | None,
    data_dir: Any,
) -> None:
    @app.action("ticket_create_slack")
    def handle_slack(ack: Any, body: dict, client: Any) -> None:
        _handle_choice(ack, body, client, target="slack_list")

    @app.action("ticket_create_jira")
    def handle_jira(ack: Any, body: dict, client: Any) -> None:
        _handle_choice(ack, body, client, target="jira")

    def _handle_choice(ack: Any, body: dict, client: Any, *, target: TicketCreateTarget) -> None:
        ack()
        if session_store is None:
            return
        channel_id = str((body.get("channel") or {}).get("id") or "")
        user_id = str((body.get("user") or {}).get("id") or "")
        message = body.get("message") or {}
        thread_ts = str(message.get("thread_ts") or message.get("ts") or "")
        action = (body.get("actions") or [{}])[0]
        raw_value = str(action.get("value") or target)
        decoded = decode_button_session_value(raw_value)
        if decoded:
            session_key, target = decoded
            session = session_store.load(session_key)
        else:
            from backend.models.session import session_key_for_task

            session_key = session_key_for_task("slack", channel_id, thread_ts)
            session = session_store.load(session_key)

        task = task_from_pending_session(
            session,
            channel_id=channel_id,
            thread_ts=thread_ts,
            user_id=user_id,
            target=target,
        )
        if task is None:
            try:
                client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text="That choice expired — mention @alfred again with your create request.",
                )
            except Exception:
                logger.exception("Failed to post expired disambiguation message")
            return

        session_store.save(session)
        _update_choice_message(client, body, target)

        from backend.integrations.slack.status import ThinkingIndicator

        indicator = ThinkingIndicator(
            client,
            channel=channel_id,
            thread_ts=thread_ts,
            loading_messages=processor.config.slack.loading_messages or None,
        )
        indicator.start()
        worker = threading.Thread(
            target=_process_resumed_task,
            args=(task, processor, indicator, client),
            daemon=True,
            name=f"alfred-ticket-choice-{task.id[:8]}",
        )
        worker.start()


def _update_choice_message(client: Any, body: dict, target: TicketCreateTarget) -> None:
    channel_id = str((body.get("channel") or {}).get("id") or "")
    message = body.get("message") or {}
    ts = str(message.get("ts") or "")
    label = "Slack List" if target == "slack_list" else "JIRA"
    try:
        client.chat_update(
            channel=channel_id,
            ts=ts,
            text=f"Creating in {label}…",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f":white_check_mark: *{label}* — working on it…",
                    },
                }
            ],
        )
    except Exception:
        logger.debug("Could not update disambiguation message", exc_info=True)


def _process_resumed_task(task: Task, processor: Any, indicator: Any, client: Any) -> None:
    from backend.formatting.file_exports import prepare_slack_delivery
    from backend.formatting.render import render_for_channel
    from backend.integrations.slack.users import SlackUserResolver, resolve_user_ids_in_text
    from backend.routing.ticket_create_disambiguation import slack_blocks_from_response

    try:
        response = processor.process(task)
        rendered = render_for_channel(response, "slack")
        rendered = resolve_user_ids_in_text(rendered, SlackUserResolver(client))
        delivery = prepare_slack_delivery(rendered, task.cleaned_intent)
        indicator.finish(delivery.text, files=delivery.files, blocks=delivery.blocks)
    except Exception as exc:
        logger.exception("Failed to process ticket create choice %s", task.id)
        indicator.finish(f"Sorry, I hit an error: {exc}")
