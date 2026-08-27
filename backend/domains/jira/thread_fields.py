"""Fill JIRA create/update fields from Slack thread and user text.

The model often passes schema placeholders like ``<to be provided by user>``
when the user only said "create on TECH board". Refuse those and infer work
from the thread or the rest of the message.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

from backend.domains.slack_board.formatting import is_weak_board_task_title
from backend.models.task import Task

_PLACEHOLDER_RE = re.compile(
    r"<\s*(?:to be provided by user|optional details from user|insert\b|placeholder|your .+ here|todo)\s*>",
    re.I,
)
_BARE_PLACEHOLDER_RE = re.compile(r"^\s*<?(?:tbd|n/?a|todo|none|placeholder)>?\s*$", re.I)
_CREATE_COMMAND_RE = re.compile(
    r"^(?:please\s+)?(?:can you\s+)?(?:create|open|file|raise|log)\s+"
    r"(?:a\s+)?(?:ticket|task|issue)\b",
    re.I,
)
_DESTINATION_ONLY_RE = re.compile(
    r"^(?:the\s+)?(?:jira\s+)?(?:tech|ts)(?:\s+board)?(?:\s+on\s+jira)?$"
    r"|^(?:the\s+)?(?:tech|ts)\s+board(?:\s+on\s+jira)?$"
    r"|^(?:jira\s+)?(?:tech|ts)\s+project$",
    re.I,
)
_KEY_EMDASH_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\s*[—–-]\s*(.+)$")
_META_LINE_RE = re.compile(
    r"^(?:to do|in progress|done|task|medium|high|low)(?:\s*[·|,].*)?$",
    re.I,
)
_ISSUE_LINE_RE = re.compile(r"(?im)\bissue:\s*(.+)$")
_SUMMARY_LINE_RE = re.compile(r"(?im)\bsummary:\s*(.+)$")
_UPDATE_TAIL_RE = re.compile(
    r",?\s*(?:using this\s+)?(?:pls|please)?\s*(?:update|modify|edit|fix)\s+"
    r"[A-Z][A-Z0-9]+\s*-?\s*\d+\s*$",
    re.I,
)
_UPDATE_HEAD_RE = re.compile(
    r"^@?\S+\s+(?:please\s+)?(?:modify|update|edit|fix)\s+[A-Z][A-Z0-9]+\s*-?\s*\d+"
    r"(?:\s+with(?:\s+proper)?\s+details?)?\s*",
    re.I,
)
_BOT_CONFIRM_RE = re.compile(
    r"created\s+`?[A-Z][A-Z0-9]+-\d+|jira_create_issue|open in jira"
    r"|i couldn.?t verify that response",
    re.I,
)
_SLACK_INDEX_RE = re.compile(r"^\[\d+\]\s*")
_SLACK_AUTHOR_RE = re.compile(r"^[^:]{1,48}:\s+")


def is_placeholder_jira_text(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return True
    if _PLACEHOLDER_RE.search(raw) or _BARE_PLACEHOLDER_RE.match(raw):
        return True
    return False


def is_weak_jira_summary(summary: str) -> bool:
    text = re.sub(r"\s+", " ", (summary or "").strip())
    if is_placeholder_jira_text(text):
        return True
    if is_weak_board_task_title(text):
        return True
    if _DESTINATION_ONLY_RE.match(text.strip(" .,:;\"'?!") or ""):
        return True
    if _CREATE_COMMAND_RE.search(text) and len(text.split()) <= 16:
        return True
    if re.search(r"\b(?:tech|ts)\s+board\b", text, re.I) and len(text.split()) <= 8:
        return True
    if re.search(r"\bon\s+(?:the\s+)?(?:jira\s+)?(?:tech|ts)\s+board\b", text, re.I) and len(text.split()) <= 16:
        return True
    return False


def extract_update_body(text: str) -> str:
    """Keep the problem statement; drop 'update TECH-363' command wrappers."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    cleaned = _UPDATE_TAIL_RE.sub("", cleaned).strip()
    cleaned = _UPDATE_HEAD_RE.sub("", cleaned).strip(" ,")
    if is_placeholder_jira_text(cleaned) or is_weak_jira_summary(cleaned):
        return ""
    return cleaned


def infer_summary_from_text(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    for pattern in (_ISSUE_LINE_RE, _SUMMARY_LINE_RE):
        match = pattern.search(raw)
        if match:
            line = _clean_work_line(match.group(1))
            if line and not is_weak_jira_summary(line):
                return line[:160]
    for line in raw.splitlines():
        emdash = _KEY_EMDASH_RE.search(_clean_work_line(line))
        if emdash:
            title = _clean_work_line(emdash.group(1))
            if title and not is_weak_jira_summary(title) and not is_placeholder_jira_text(title):
                return title[:160]
    for line in raw.splitlines():
        candidate = _clean_work_line(line)
        if len(candidate) < 12 or _is_noise_line(candidate):
            continue
        if _META_LINE_RE.match(candidate):
            continue
        if is_weak_jira_summary(candidate) or is_placeholder_jira_text(candidate):
            continue
        return candidate[:160]
    return ""


def fill_jira_create_args(
    args: dict[str, Any],
    *,
    request_text: str = "",
    thread_text: str = "",
    session_title: str = "",
) -> dict[str, Any]:
    filled = dict(args)
    summary = str(filled.get("summary") or "").strip()
    description = str(filled.get("description") or "").strip()
    if is_placeholder_jira_text(description):
        description = ""
        filled["description"] = ""

    if is_weak_jira_summary(summary):
        summary = infer_summary_from_text(thread_text)
        if is_weak_jira_summary(summary):
            from backend.routing.slack_board.intent import extract_task_title

            summary = extract_task_title(thread_text)
        if is_weak_jira_summary(summary) and not is_weak_jira_summary(session_title):
            summary = session_title.strip()
        if is_weak_jira_summary(summary):
            summary = infer_summary_from_text(request_text) or extract_task_title_safe(request_text)
        filled["summary"] = summary

    if not description.strip() or is_placeholder_jira_text(description):
        body = extract_update_body(request_text)
        if len(body) < 40:
            body = _thread_work_excerpt(thread_text) or body
        if body and not is_placeholder_jira_text(body):
            filled["description"] = body
    return filled


def fill_jira_update_args(
    args: dict[str, Any],
    *,
    request_text: str = "",
    thread_text: str = "",
) -> dict[str, Any]:
    filled = dict(args)
    summary = str(filled.get("summary") or "").strip()
    description = filled.get("description")
    desc_text = str(description).strip() if description is not None else ""
    body = extract_update_body(request_text)
    if len(body) < 40:
        body = extract_update_body(thread_text) or _thread_work_excerpt(thread_text)

    if is_weak_jira_summary(summary) or is_placeholder_jira_text(summary):
        inferred = infer_summary_from_text(body or request_text or thread_text)
        if inferred:
            filled["summary"] = inferred

    if description is None or is_placeholder_jira_text(desc_text):
        if body and not is_placeholder_jira_text(body):
            filled["description"] = body
            filled["replace_description"] = True
    return filled


def extract_task_title_safe(text: str) -> str:
    from backend.routing.slack_board.intent import extract_task_title

    title = extract_task_title(text)
    return "" if is_weak_jira_summary(title) else title


def _is_noise_line(line: str) -> bool:
    if _BOT_CONFIRM_RE.search(line):
        return True
    stripped = re.sub(r"^@\S+\s+", "", line).strip()
    if _CREATE_COMMAND_RE.search(stripped) or is_weak_jira_summary(stripped):
        return True
    if is_placeholder_jira_text(line) or is_weak_jira_summary(line):
        return True
    return False


def _clean_work_line(line: str) -> str:
    text = (line or "").strip().strip("-•*")
    text = _SLACK_INDEX_RE.sub("", text)
    text = _SLACK_AUTHOR_RE.sub("", text, count=1)
    return text.strip()


def _thread_work_excerpt(thread_text: str, *, max_chars: int = 3500) -> str:
    lines: list[str] = []
    for raw in (thread_text or "").splitlines():
        line = _clean_work_line(raw)
        if not line or _is_noise_line(line):
            continue
        if is_placeholder_jira_text(line) or is_weak_jira_summary(line):
            continue
        lines.append(line)
    return "\n".join(lines).strip()[:max_chars]


def fetch_slack_thread_text(ctx: Any, task: Task | None) -> str:
    channel = str((task.channel_id if task else "") or getattr(ctx, "channel_id", "") or "").strip()
    ts = str((task.thread_ts if task else "") or getattr(ctx, "thread_ts", "") or "").strip()
    if not channel or not ts:
        return ""
    slack = getattr(getattr(ctx, "config", None), "slack", None)
    token = str(getattr(slack, "bot_token", "") or "").strip()
    if not token:
        return ""
    try:
        from slack_sdk import WebClient

        from backend.integrations.slack.context import fetch_thread_messages, messages_to_text
        from backend.routing.slack_board.bootstrap import _bot_user_id

        client = WebClient(token=token)
        proxy = task or SimpleNamespace(channel_id=channel, thread_ts=ts)
        messages = fetch_thread_messages(
            client,
            proxy,  # type: ignore[arg-type]
            limit=50,
            bot_user_id=_bot_user_id(client),
        )
        return messages_to_text(messages) or ""
    except Exception:
        return ""
