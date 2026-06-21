"""Thinking indicator via Slack Assistant API (no message edit badge)."""

from __future__ import annotations

import logging
import random
from typing import Any

logger = logging.getLogger(__name__)

# Catchy loading lines — Slack rotates up to 10 via loading_messages.
STATUS_LINES: list[tuple[str, str]] = [
    ("🍳", "I am cooking…"),
    ("🦇", "Batman is searching for Joker in Gotham…"),
    ("🏗️", "Building response…"),
    ("🚀", "Hacking NASA…"),
    ("🔥", "Trimming firewall…"),
    ("🔍", "Grepping the multiverse…"),
    ("☕", "Deploying caffeine to prod…"),
    ("📜", "Reading stack traces so you don't have to…"),
    ("🤖", "Asking the local model nicely…"),
    ("🧭", "Triangulating the root cause…"),
    ("🛠️", "Tuning the flux capacitor…"),
    ("🗺️", "Mapping dependencies…"),
]

MAX_LOADING_MESSAGES = 10
ASSISTANT_STATUS = "is thinking…"


def loading_messages_for_slack(*, count: int = MAX_LOADING_MESSAGES) -> list[str]:
    """Build loading_messages for assistant.threads.setStatus (max 10)."""
    pool = [f"{emoji} {line}" for emoji, line in STATUS_LINES]
    if len(pool) <= count:
        return pool
    return random.sample(pool, count)


class ThinkingIndicator:
    """Show Assistant thread status while thinking; post final reply as a new message."""

    def __init__(
        self,
        client: Any,
        *,
        channel: str,
        thread_ts: str | None,
    ) -> None:
        self.client = client
        self.channel = channel
        self.thread_ts = thread_ts
        self._assistant_active = False
        self._legacy_message_ts: str | None = None

    def start(self) -> None:
        if not self.thread_ts:
            return
        if self._try_assistant_status():
            self._assistant_active = True
            logger.debug("Assistant setStatus active for channel=%s thread=%s", self.channel, self.thread_ts)
            return
        self._start_legacy_placeholder()

    def finish(self, text: str, *, files: list[Any] | None = None) -> None:
        if self._assistant_active:
            self._clear_assistant_status()
            self._post_reply(text, files=files)
            return
        self._finish_legacy(text, files=files)

    def _post_reply(self, text: str, *, files: list[Any] | None = None) -> None:
        from backend.ingress.file_exports import SlackFileAttachment
        from backend.slack.files import upload_slack_files

        attachments = [item for item in (files or []) if isinstance(item, SlackFileAttachment)]
        if attachments:
            upload_slack_files(
                self.client,
                channel=self.channel,
                thread_ts=self.thread_ts,
                files=attachments,
            )
        self.client.chat_postMessage(
            channel=self.channel,
            thread_ts=self.thread_ts,
            text=text,
        )

    def _try_assistant_status(self) -> bool:
        if not hasattr(self.client, "assistant_threads_setStatus"):
            return False
        try:
            response = self.client.assistant_threads_setStatus(
                channel_id=self.channel,
                thread_ts=self.thread_ts,
                status=ASSISTANT_STATUS,
                loading_messages=loading_messages_for_slack(),
            )
            return bool(response.get("ok"))
        except Exception:
            logger.warning("assistant.threads.setStatus unavailable, using legacy placeholder", exc_info=True)
            return False

    def _clear_assistant_status(self) -> None:
        try:
            self.client.assistant_threads_setStatus(
                channel_id=self.channel,
                thread_ts=self.thread_ts,
                status="",
            )
        except Exception:
            logger.debug("Failed to clear assistant status", exc_info=True)

    def _start_legacy_placeholder(self) -> None:
        """Fallback when Assistant API is unavailable (shows edited badge on update)."""
        emoji, line = random.choice(STATUS_LINES)
        response = self.client.chat_postMessage(
            channel=self.channel,
            thread_ts=self.thread_ts,
            text=f"{emoji}  _{line}_",
        )
        self._legacy_message_ts = response.get("ts")

    def _finish_legacy(self, text: str, *, files: list[Any] | None = None) -> None:
        from backend.ingress.file_exports import SlackFileAttachment
        from backend.slack.files import upload_slack_files

        attachments = [item for item in (files or []) if isinstance(item, SlackFileAttachment)]
        if self._legacy_message_ts:
            try:
                self.client.chat_update(
                    channel=self.channel,
                    ts=self._legacy_message_ts,
                    text=text,
                )
                if attachments:
                    upload_slack_files(
                        self.client,
                        channel=self.channel,
                        thread_ts=self.thread_ts,
                        files=attachments,
                    )
                return
            except Exception:
                logger.debug("Legacy status update failed, posting new message", exc_info=True)
        self._post_reply(text, files=attachments)
