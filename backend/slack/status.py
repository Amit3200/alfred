"""Thinking indicator via Slack Assistant API (no message edit badge)."""

from __future__ import annotations

import logging
import random
import re
import threading
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
STATUS_ROTATION_SECONDS = 2.0
_SLACK_EMOJI_PREFIX_RE = re.compile(r"^:\w+:\s*")


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


def loading_line_to_status(line: str) -> str:
    """Convert a loading line into assistant status text (shown as 'alfred {status}')."""
    text = _SLACK_EMOJI_PREFIX_RE.sub("", line.strip())
    while text and ord(text[0]) > 0x2600:
        text = text[1:].lstrip()
    text = text.strip()
    if not text:
        return ASSISTANT_STATUS
    lower = text.lower()
    if lower.startswith("is "):
        return text
    if lower.startswith("i am "):
        return f"is {text[5:]}"
    if lower.startswith("i "):
        return f"is {text[2:]}"
    return f"is {text[0].lower()}{text[1:]}" if text else ASSISTANT_STATUS


class ThinkingIndicator:
    """Show Assistant thread status while thinking; post final reply as a new message."""

    def __init__(
        self,
        client: Any,
        *,
        channel: str,
        thread_ts: str | None,
        loading_messages: list[str] | None = None,
        rotation_seconds: float = STATUS_ROTATION_SECONDS,
    ) -> None:
        self.client = client
        self.channel = channel
        self.thread_ts = thread_ts
        self._loading_messages = loading_messages
        self._rotation_seconds = rotation_seconds
        self._status_pool: list[str] = []
        self._assistant_active = False
        self._legacy_message_ts: str | None = None
        self._stop_rotation = threading.Event()
        self._rotation_thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.thread_ts:
            return
        self._status_pool = loading_messages_for_slack(custom_lines=self._loading_messages)
        if self._try_assistant_status(self._status_pool[0] if self._status_pool else ASSISTANT_STATUS):
            self._assistant_active = True
            self._start_rotation()
            logger.debug("Assistant setStatus active for channel=%s thread=%s", self.channel, self.thread_ts)
            return
        self._start_legacy_placeholder()

    def finish(self, text: str, *, files: list[Any] | None = None) -> None:
        self._stop_rotation_thread()
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

    def _try_assistant_status(self, line: str) -> bool:
        if not hasattr(self.client, "assistant_threads_setStatus"):
            return False
        try:
            response = self.client.assistant_threads_setStatus(
                channel_id=self.channel,
                thread_ts=self.thread_ts,
                status=loading_line_to_status(line),
                loading_messages=self._status_pool[:MAX_LOADING_MESSAGES],
            )
            return bool(response.get("ok"))
        except Exception:
            logger.warning("assistant.threads.setStatus unavailable, using legacy placeholder", exc_info=True)
            return False

    def _set_assistant_status(self, line: str) -> None:
        try:
            self.client.assistant_threads_setStatus(
                channel_id=self.channel,
                thread_ts=self.thread_ts,
                status=loading_line_to_status(line),
                loading_messages=self._status_pool[:MAX_LOADING_MESSAGES],
            )
        except Exception:
            logger.debug("Failed to refresh assistant status", exc_info=True)

    def _start_rotation(self) -> None:
        if not self._assistant_active or len(self._status_pool) <= 1:
            return
        self._stop_rotation.clear()
        self._rotation_thread = threading.Thread(
            target=self._rotate_status,
            daemon=True,
            name="alfred-slack-status",
        )
        self._rotation_thread.start()

    def _rotate_status(self) -> None:
        pool = self._status_pool
        index = 0
        while not self._stop_rotation.wait(self._rotation_seconds):
            index = (index + 1) % len(pool)
            self._set_assistant_status(pool[index])

    def _stop_rotation_thread(self) -> None:
        self._stop_rotation.set()
        if self._rotation_thread and self._rotation_thread.is_alive():
            self._rotation_thread.join(timeout=1.0)
        self._rotation_thread = None

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
        line = random.choice(self._status_pool or _default_status_lines())
        response = self.client.chat_postMessage(
            channel=self.channel,
            thread_ts=self.thread_ts,
            text=f"_{line}_",
        )
        self._legacy_message_ts = response.get("ts")
        if len(self._status_pool) > 1:
            self._start_legacy_rotation()

    def _start_legacy_rotation(self) -> None:
        self._stop_rotation.clear()
        self._rotation_thread = threading.Thread(
            target=self._rotate_legacy_placeholder,
            daemon=True,
            name="alfred-slack-status-legacy",
        )
        self._rotation_thread.start()

    def _rotate_legacy_placeholder(self) -> None:
        pool = self._status_pool or _default_status_lines()
        index = 0
        while not self._stop_rotation.wait(self._rotation_seconds):
            if not self._legacy_message_ts:
                return
            index = (index + 1) % len(pool)
            try:
                self.client.chat_update(
                    channel=self.channel,
                    ts=self._legacy_message_ts,
                    text=f"_{pool[index]}_",
                )
            except Exception:
                logger.debug("Legacy status rotation failed", exc_info=True)
                return

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
