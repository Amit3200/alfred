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
MAX_SLACK_LOADING_MESSAGE_LENGTH = 50
ASSISTANT_STATUS = "is thinking…"
STATUS_ROTATION_SECONDS = 3.0
_SLACK_EMOJI_PREFIX_RE = re.compile(r"^:[\w-]+:\s*")
_ACTIVE_BY_THREAD: dict[str, Any] = {}
_THREAD_LOCK = threading.Lock()


def _split_loading_prefix(line: str) -> tuple[str, str]:
    """Split a loading line into emoji prefix and body text."""
    text = line.strip()
    match = _SLACK_EMOJI_PREFIX_RE.match(text)
    if match:
        return match.group(0).rstrip(), text[match.end() :].strip()
    index = 0
    while index < len(text):
        codepoint = ord(text[index])
        if codepoint <= 0x2600 and text[index] not in "\ufe0f\u200d":
            break
        index += 1
    if index == 0:
        return "", text
    return text[:index].strip(), text[index:].lstrip()


def _fit_loading_message(prefix: str, body: str) -> str:
    """Build a loading message that fits Slack's 50-character limit."""
    if not prefix:
        if len(body) <= MAX_SLACK_LOADING_MESSAGE_LENGTH:
            return body
        return body[: MAX_SLACK_LOADING_MESSAGE_LENGTH - 1].rstrip() + "…"
    if not body:
        return prefix[:MAX_SLACK_LOADING_MESSAGE_LENGTH]
    message = f"{prefix} {body}"
    if len(message) <= MAX_SLACK_LOADING_MESSAGE_LENGTH:
        return message
    budget = MAX_SLACK_LOADING_MESSAGE_LENGTH - len(prefix) - 2  # space + ellipsis
    if budget < 1:
        return prefix[:MAX_SLACK_LOADING_MESSAGE_LENGTH]
    return f"{prefix} {body[:budget].rstrip()}…"


def slack_shortcode_prefix(line: str) -> str | None:
    """Return workspace emoji shortcode at the start of a line, if any."""
    match = _SLACK_EMOJI_PREFIX_RE.match(line.strip())
    if not match:
        return None
    name = match.group(0).strip().strip(":")
    return f":{name}:" if name else None


def pool_has_custom_shortcodes(lines: list[str]) -> bool:
    """True when loading lines use :workspace-emoji: shortcodes."""
    return any(slack_shortcode_prefix(line) for line in lines)


def _thread_key(channel: str, thread_ts: str) -> str:
    return f"{channel}:{thread_ts}"


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

    if len(custom) >= count:
        return custom[:count]
    remaining = count - len(custom)
    if len(defaults) <= remaining:
        return custom + defaults
    return custom + random.sample(defaults, remaining)


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


def slack_loading_messages(lines: list[str]) -> list[str]:
    """Fit loading_messages for assistant.threads.setStatus (max 50 chars, keep emojis)."""
    sanitized: list[str] = []
    for line in lines[:MAX_LOADING_MESSAGES]:
        original = line.strip()
        prefix, body = _split_loading_prefix(original)
        sanitized.append(_fit_loading_message(prefix, body or original))
    return sanitized


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
        self._slack_loading_messages: list[str] = []
        self._status_text = ASSISTANT_STATUS
        self._superseded = False
        self._assistant_active = False
        self._legacy_message_ts: str | None = None
        self._stop_rotation = threading.Event()
        self._rotation_thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.thread_ts:
            return
        key = _thread_key(self.channel, self.thread_ts)
        with _THREAD_LOCK:
            previous = _ACTIVE_BY_THREAD.get(key)
            if previous is not None and previous is not self:
                previous._supersede()
            _ACTIVE_BY_THREAD[key] = self

        self._status_pool = loading_messages_for_slack(custom_lines=self._loading_messages)
        self._slack_loading_messages = slack_loading_messages(self._status_pool)
        first_line = self._status_pool[0] if self._status_pool else ASSISTANT_STATUS
        self._status_text = loading_line_to_status(first_line)
        use_assistant = (
            not pool_has_custom_shortcodes(self._status_pool)
            and self._try_assistant_status()
        )
        if use_assistant:
            self._assistant_active = True
            logger.info(
                "Slack thinking: using assistant.threads.setStatus (channel=%s thread=%s)",
                self.channel,
                self.thread_ts,
            )
            return
        if pool_has_custom_shortcodes(self._status_pool):
            logger.info(
                "Slack thinking: using thread placeholder for custom emoji lines "
                "(channel=%s thread=%s)",
                self.channel,
                self.thread_ts,
            )
        else:
            logger.info(
                "Slack thinking: falling back to placeholder message (channel=%s thread=%s)",
                self.channel,
                self.thread_ts,
            )
        self._start_legacy_placeholder()

    def _supersede(self) -> None:
        self._superseded = True
        self._stop_rotation_thread()

    def finish(self, text: str, *, files: list[Any] | None = None) -> None:
        self._stop_rotation_thread()
        if self.thread_ts:
            key = _thread_key(self.channel, self.thread_ts)
            with _THREAD_LOCK:
                if _ACTIVE_BY_THREAD.get(key) is self:
                    del _ACTIVE_BY_THREAD[key]
        if self._assistant_active:
            # Slack clears assistant status automatically when the app posts a reply.
            self._post_reply(text, files=files)
            self._clear_assistant_status()
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

    def _set_status_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "channel_id": self.channel,
            "thread_ts": self.thread_ts,
            "status": self._status_text,
        }
        if self._slack_loading_messages:
            kwargs["loading_messages"] = self._slack_loading_messages
        return kwargs

    def _try_assistant_status(self) -> bool:
        if not hasattr(self.client, "assistant_threads_setStatus"):
            logger.info(
                "Slack thinking: assistant.threads.setStatus not available on client — "
                "upgrade slack-sdk (>=3.37) and slack-bolt (>=1.26)"
            )
            return False
        payload = self._set_status_kwargs()
        status = payload["status"]
        try:
            response = self._call_set_status(**payload)
            if response.get("ok"):
                return True
            error = response.get("error") or "unknown_error"
            logger.warning(
                "assistant.threads.setStatus rejected (%s) for channel=%s thread=%s",
                error,
                self.channel,
                self.thread_ts,
            )
            if payload.get("loading_messages"):
                return self._retry_set_status_without_loading_messages(status)
            return False
        except Exception as exc:
            if payload.get("loading_messages") and self._is_set_status_argument_error(exc):
                logger.warning(
                    "assistant.threads.setStatus loading_messages rejected (%s) — retrying status only",
                    exc,
                )
                return self._retry_set_status_without_loading_messages(status)
            logger.warning(
                "assistant.threads.setStatus unavailable (%s) — using placeholder message. "
                "Ensure assistant:write scope, Agents & AI Apps enabled, and reinstall the app.",
                exc,
            )
            return False

    def _call_set_status(self, **kwargs: Any) -> dict[str, Any]:
        return self.client.assistant_threads_setStatus(**kwargs)

    @staticmethod
    def _is_set_status_argument_error(exc: Exception) -> bool:
        from slack_sdk.errors import SlackApiError

        if isinstance(exc, SlackApiError):
            body = getattr(exc, "response", None)
            data = getattr(body, "data", None) if body is not None else None
            if isinstance(data, dict) and data.get("error") == "invalid_arguments":
                return True
        message = str(exc).lower()
        return "invalid_arguments" in message or "must be less than 51 characters" in message

    def _retry_set_status_without_loading_messages(self, status: str) -> bool:
        try:
            retry = self._call_set_status(
                channel_id=self.channel,
                thread_ts=self.thread_ts,
                status=status,
            )
            if retry.get("ok"):
                logger.info("assistant.threads.setStatus succeeded without loading_messages")
                self._slack_loading_messages = []
                return True
            logger.warning(
                "assistant.threads.setStatus retry failed (%s)",
                retry.get("error") or "unknown_error",
            )
        except Exception as exc:
            logger.warning("assistant.threads.setStatus retry failed (%s)", exc)
        return False

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
        """Fallback when Assistant API is unavailable or custom :emoji: lines are configured."""
        pool = self._status_pool or _default_status_lines()
        line = pool[0]
        response = self.client.chat_postMessage(
            channel=self.channel,
            thread_ts=self.thread_ts,
            text=f"_{line}_",
        )
        self._legacy_message_ts = response.get("ts")
        if len(pool) > 1:
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
            if self._superseded or not self._legacy_message_ts:
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
                self.client.chat_delete(channel=self.channel, ts=self._legacy_message_ts)
            except Exception:
                logger.debug("Could not delete legacy thinking placeholder", exc_info=True)
            self._legacy_message_ts = None
        self._post_reply(text, files=attachments)
