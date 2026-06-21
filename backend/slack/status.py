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
    # Cats
    ("🐱", "Judging your query from atop the keyboard…"),
    ("😺", "Purring through the logs…"),
    ("🐈", "Knocking your priorities off the desk…"),
    ("😸", "Cat is sitting on the router again…"),
    ("🙀", "Staring at the void (and the error message)…"),
    # Alfred / butler
    ("🎩", "I am just a butler…"),
    ("🍵", "Polishing the silver while the servers spin…"),
    ("🦹", "Trying to become vengeance…"),
    ("🦸", "Fighting Superman with kryptonite…"),
    ("🕷️", "Contacting Spider-Man…"),
    ("🦾", "Borrowing something from Iron Man…"),
    ("💰", "Drafting a pay-raise request to Bruce Wayne…"),
    ("📋", "Some men just want to watch the world grep…"),
    # Life & chaos
    ("🕳️", "Filling potholes on the information superhighway…"),
    ("🌍", "Fighting global warming one query at a time…"),
    ("♟️", "Asking Samay for life goals…"),
    ("💻", "Grinding LeetCode instead of your ticket…"),
    ("⚔️", "Fighting AI in the parking lot…"),
    ("🧠", "Negotiating with the singularity…"),
    ("🎬", "This is Alfred. I am inevitable…"),
    # More pop culture & tech
    ("⚡", "Waiting for Gandalf to arrive at prod…"),
    ("💍", "One does not simply deploy to Mordor…"),
    ("🐍", "There is no spoon — only stack overflow…"),
    ("🧙", "You shall not pass… without unit tests…"),
    ("🎮", "Press F to pay respects to the build…"),
    ("🖖", "Live long and grep prosper…"),
    ("👾", "Pac-Man is eating the latency spikes…"),
    ("🎸", "Smells like teen spirit (and stale coffee)…"),
    ("🧊", "Let it go… let it cache…"),
    ("🐉", "Training dragons on your dataset…"),
    ("🎯", "Winter is coming — bundle up the deps…"),
    ("🍕", "Deploying pizza to the on-call engineer…"),
    ("🧪", "Breaking bad… habits in the codebase…"),
    ("🎪", "This is fine. Everything is fine. Checking logs…"),
    ("🏃", "Running from responsibility at O(n) speed…"),
    ("🎰", "Spinning up another microservice…"),
    ("🦥", "Moving at sloth speed through the backlog…"),
    ("🎱", "Shaken, not stirred — mixing the API response…"),
    ("🚕", "Follow the yellow brick stack trace…"),
    ("🔮", "Consulting the oracle (it said try again)…"),
]

MAX_LOADING_MESSAGES = 10
ASSISTANT_STATUS = "is thinking…"


def _default_status_lines() -> list[str]:
    return [f"{emoji} {line}" for emoji, line in STATUS_LINES]


def loading_messages_for_slack(
    *,
    custom_lines: list[str] | None = None,
    count: int = MAX_LOADING_MESSAGES,
) -> list[str]:
    """Build loading_messages for assistant.threads.setStatus (max 10)."""
    custom = [line.strip() for line in (custom_lines or []) if line and line.strip()]
    defaults = _default_status_lines()
    pool = custom + defaults

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
        loading_messages: list[str] | None = None,
    ) -> None:
        self.client = client
        self.channel = channel
        self.thread_ts = thread_ts
        self._loading_messages = loading_messages
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
                loading_messages=loading_messages_for_slack(custom_lines=self._loading_messages),
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
        line = random.choice(
            loading_messages_for_slack(custom_lines=self._loading_messages, count=MAX_LOADING_MESSAGES)
        )
        response = self.client.chat_postMessage(
            channel=self.channel,
            thread_ts=self.thread_ts,
            text=f"_{line}_",
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
