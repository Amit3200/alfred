"""Parse Slack board task intents and thread context."""

from __future__ import annotations

import re
from typing import Any

from backend.domains.slack_board.formatting import (
    DEFAULT_BOARD_SEVERITY,
    build_board_task_details,
    finalize_board_create_fields,
    humanize_board_task_text,
    is_weak_board_task_title,
    normalize_board_severity,
    slack_thread_permalink,
)
from backend.models.task import Task

_CREATE_TASK_RE = re.compile(
    r"\b(?:create|add|open|file|raise|log)\b.{0,48}\b(?:a\s+)?(?:tasks?|tickets?|items?|bugs?)\b",
    re.I,
)
_UPDATE_STATUS_RE = re.compile(
    r"\b(?:move|set|update|mark|change)\b.{0,40}\b(?:status|to)\b",
    re.I,
)
_ASSIGN_RE = re.compile(
    r"\b(?:assign|reassign|give)\b.{0,30}\b(?:to|@)",
    re.I,
)
_COMMENT_RE = re.compile(
    r"\b(?:comment|note|reply|add)\b.{0,30}\b(?:on|to|in)\b.{0,20}\b(?:task|ticket|thread)\b",
    re.I,
)
_SEARCH_RE = re.compile(
    r"\b(?:list|show|find|search|what(?:'s| is)|summarize)\b.{0,30}\b(?:task|ticket|bug|open|board)\b",
    re.I,
)
_CONFIG_STATUS_RE = re.compile(
    r"\b(?:configured|setup|set up|ready|linked|bound)\b.{0,40}\b(?:track|assign|task|ticket|board|list)\b"
    r"|\bcan you see if\b.{0,60}\b(?:configured|setup|track|assign|task|ticket|board|list)\b"
    r"|\b(?:is|are)\s+(?:this|we|it|alfred|the channel)\b.{0,40}\b(?:configured|setup|ready|linked)\b"
    r"|\b(?:does|do)\s+(?:this|alfred|we)\b.{0,30}\b(?:track|assign)\b.{0,20}\b(?:task|ticket)\b",
    re.I,
)
_ABOVE_RE = re.compile(
    r"\b(?:for\s+)?(?:the\s+)?(?:above|this|below|here|same\s+thread|in\s+this\s+thread)\b",
    re.I,
)
_BATCH_CREATE_RE = re.compile(
    r"\b(?:all|each)\s+(?:of\s+)?(?:the\s+)?(?:above|these|those|them|following)\b"
    r"|\bthese\s+(?:issues|items|tasks|tickets|bugs)\b"
    r"|\bcreate\s+tasks\b"
    r"|\bfollowing\s+tasks?\b"
    r"|\beach\s+(?:item|one|task)\b.{0,32}\bseparate\b"
    r"|\bseparate\s+tasks?\b",
    re.I,
)
_NUMBERED_ITEM_RE = re.compile(
    r"^\s*(?:(?:\d+|[A-Za-z])[\.\)\-]\s+|[-*•]\s+)(.+)$",
)
_CREATE_COMMAND_LINE_RE = re.compile(
    r"@alfred\b|\bcreate\s+(?:a\s+)?(?:task|ticket|item)s?\b",
    re.I,
)
_BATCH_METADATA_LINE_RE = re.compile(
    r"^(?:list|board|status|severity|assignee|record|open list|display id|"
    r"planned action|governance|could not create)\s*:",
    re.I,
)
_BATCH_TITLE_NOISE_RE = re.compile(
    r"requires explicit approval"
    r"|slack_board_[a-z_]+"
    r"|jira_create_issue"
    r"|tasks? created on your board"
    r"|write actions approved"
    r"|yes,\s*proceed",
    re.I,
)
_CREATED_TASK_LINE_RE = re.compile(
    r"^\*{0,2}(?:[A-Z]{1,8}-\d+|Rec[A-Za-z0-9]+)\*{0,2}\s*[·•]",
    re.I,
)
_TICKET_REF_RE = re.compile(
    r"\b((?:[A-Z]{1,8}-\d+|Rec[A-Za-z0-9]+))\b",
    re.I,
)
_LIST_ID_OVERRIDE_RE = re.compile(
    r"\b(?:on|using|with|from)\s+(?:the\s+)?list(?:\s+id)?\s+(F[A-Za-z0-9]+)\b"
    r"|\blist(?:\s+id)?\s*[:=]\s*(F[A-Za-z0-9]+)\b",
    re.I,
)
_KNOWN_PLACEHOLDER_LIST_IDS = frozenset(
    {
        "F0123ABCDEF",
        "F01234567",
        "F012345678",
    }
)
_TITLE_FOR_RE = re.compile(
    r"\b(?:create|add|open|file)\b.{0,20}\b(?:task|ticket)\b.{0,20}\b(?:for|about)\s+"
    r"(.+?)(?:\s+for\s+(?:the\s+)?above|\s+in\s+this|\s*$)",
    re.I,
)


def is_placeholder_list_id(list_id: str) -> bool:
    """Detect doc/example List ids that should never be used in production."""
    lid = (list_id or "").strip().upper()
    if not lid.startswith("F"):
        return False
    if lid in _KNOWN_PLACEHOLDER_LIST_IDS:
        return True
    # Common docs/UI examples: F0123… with only hex-ish filler after the prefix.
    if lid.startswith("F0123") and len(lid) <= 12:
        return True
    return False


def extract_list_id_override(intent: str) -> str:
    """Parse an explicit Slack List id from a create/link message."""
    match = _LIST_ID_OVERRIDE_RE.search(intent or "")
    return match.group(1).strip() if match else ""


def strip_list_id_override(intent: str) -> str:
    """Remove explicit list id phrases so they are not treated as task titles."""
    text = (intent or "").strip()
    if not text:
        return text
    return _LIST_ID_OVERRIDE_RE.sub("", text).strip(" .,:;-")


def looks_like_slack_board_config_question(intent: str) -> bool:
    return bool(_CONFIG_STATUS_RE.search(intent or ""))


def looks_like_slack_board_request(intent: str) -> bool:
    text = (intent or "").strip()
    if not text:
        return False
    if looks_like_slack_board_config_question(text):
        return True
    if _CREATE_TASK_RE.search(text):
        return True
    if _BOARD_INLINE_STATUS_RE.search(text):
        return True
    if _UPDATE_STATUS_RE.search(text) and _TICKET_REF_RE.search(text):
        return True
    if _ASSIGN_RE.search(text):
        return True
    if _COMMENT_RE.search(text):
        return True
    if _SEARCH_RE.search(text):
        return True
    if "bugs tracker" in text.lower() or "slack board" in text.lower():
        return True
    return False


_TITLE_ON_RE = re.compile(
    r"\b(?:create|add|open|file)\b.{0,20}\b(?:a\s+)?(?:task|ticket)\b.{0,15}\b(?:on|for|about)\s+"
    r"(.+?)(?:\s+as\s+(?:p0|p1|p2|p3)\b|\s+and\s+assign\b|\s*$)",
    re.I,
)
_TITLE_TO_RE = re.compile(
    r"\b(?:create|add|open|file)\b.{0,20}\b(?:a\s+)?(?:task|ticket)\b\s+to\s+"
    r"(.+?)(?:\s+and\s+assign\b|\s*$)",
    re.I,
)
_TITLE_SEP_RE = re.compile(
    r"\b(?:create|add|open|file)\b.{0,20}\b(?:a\s+)?(?:task|ticket)\b\s*"
    r"(?:[-–—:|]\s*|\b(?:named|called|titled)\s+)"
    r"(.+?)(?:\s+and\s+assign\b|\s*$)",
    re.I,
)
_CREATE_CMD_RE = re.compile(
    r"\b(?:create|add|open|file)\b.{0,20}\b(?:a\s+)?(?:task|ticket)\b",
    re.I,
)
_CREATE_ASSIGNEE_RE = re.compile(
    r"\b(?:create|add|open|file)\b.{0,40}\b(?:a\s+)?(?:task|ticket)\b.{0,40}\b(?:on|for|to)\s+<@([A-Z0-9]+)",
    re.I,
)
_ASSIGN_TO_RE = re.compile(
    r"\bassign\b.{0,24}\b(?:it\s+)?(?:to\s+)?<@([A-Z0-9]+)",
    re.I,
)
_THREAD_ACTION_ASSIGNEE_RE = re.compile(
    r"<@([A-Z0-9]+)(?:\|[^>]+)?>\s*(?:please|kindly|pls\.?|can you|could you|need to|needs to)\b",
    re.I,
)
_BOARD_TITLE_PROMPT_MARKERS = (
    "what should the task be called",
    "what should the task be named",
)
_FOLLOWUP_STATUS_RE = re.compile(
    r"\b(?:yes|yep|yeah|ok(?:ay)?)\b.{0,40}\b(?:created|done|there|it)\b"
    r"|\b(?:is|was)\s+it\s+created\b"
    r"|\b(?:did\s+(?:you|that|it)|has\s+it)\s+(?:create|work)\b"
    r"|\bcreated\s*\?\s*$",
    re.I,
)
_BOARD_INLINE_STATUS_RE = re.compile(
    r"\b(?:[A-Z]{1,8}-\d+|Rec[A-Za-z0-9]+)\b.{0,40}\b(?:is|are)\b.{0,24}"
    r"\b(?:not picked|in progress|review|done)\b",
    re.I,
)
_SEVERITY_ASSIGN_RE = re.compile(
    r"\b(?:set|assign|change|update)\b.{0,24}\bseverity\b.{0,20}\b(?:to\s+)?(?:high|medium|low|p0|p1|p2|p3)\b",
    re.I,
)
_SETUP_BOARD_RE = re.compile(
    r"\b(?:setup|set\s*up|provision|initialize|init)\b.{0,24}\b(?:board|list)\b"
    r"(?:\s+(?:named|called)\s+[\"']?([^\"'\n]{2,60})[\"']?)?"
    r"|\b(?:setup|set\s*up|provision)\b.{0,10}\b(?:this|the)\b.{0,10}\b(?:channel\s+)?(?:board|list)\b"
    r"|\bcreate\b.{0,12}\b(?:a\s+)?(?:new\s+)?(?:slack\s+)?(?:board|list)\b(?!\s*(?:task|ticket|item)\b)",
    re.I,
)
_BOARD_SESSION_MARKERS = (
    "create task",
    "create a task",
    "board task",
    "slack list",
    "slack board",
    "assign",
    "p0",
    "p1",
    "ts-",
    "rec",
    "display id",
    "created board task",
)


def looks_like_slack_board_followup(
    intent: str,
    *,
    session_turns: tuple[str, ...] = (),
    thread_context: str | None = None,
) -> bool:
    """Short thread follow-up after a board create (e.g. 'yes is it created?')."""
    if looks_like_slack_board_create(intent) or looks_like_board_where_question(intent):
        return False
    text = (intent or "").strip()
    if not text:
        return False
    if not _FOLLOWUP_STATUS_RE.search(text):
        return False
    combined = "\n".join([*session_turns[-8:], thread_context or "", text]).lower()
    return sum(1 for marker in _BOARD_SESSION_MARKERS if marker in combined) >= 1


def looks_like_slack_board_create(
    intent: str,
    *,
    channel_id: str = "",
    data_dir: Any = None,
    session_turns: tuple[str, ...] = (),
    session_metadata: dict[str, Any] | None = None,
    thread_context: str = "",
) -> bool:
    text = intent or ""
    if not _CREATE_TASK_RE.search(text):
        return False
    from backend.routing.create_target_precedence import should_route_create_to_jira

    if should_route_create_to_jira(
        text,
        jira_enabled=True,
        channel_id=channel_id,
        data_dir=data_dir,
        session_turns=session_turns,
        session_metadata=session_metadata,
        thread_context=thread_context,
    ):
        return False
    return True


def looks_like_board_create_title_followup(
    intent: str,
    *,
    session_turns: tuple[str, ...] = (),
    session_metadata: dict[str, Any] | None = None,
) -> bool:
    """User replied with a task title after Alfred asked for one."""
    if looks_like_slack_board_create(intent) or looks_like_slack_board_update(intent):
        return False
    text = re.sub(r"@alfred\b", "", intent or "", flags=re.I).strip()
    if not text or len(text) > 200:
        return False
    if re.search(r"\b(?:create|setup|link|move|unlink|show)\b.{0,12}\b(?:task|board|list)\b", text, re.I):
        return False
    if (session_metadata or {}).get("pending_board_create"):
        return True
    combined = "\n".join(session_turns[-8:]).lower()
    return any(marker in combined for marker in _BOARD_TITLE_PROMPT_MARKERS)


def extract_board_title_followup(intent: str) -> str:
    text = re.sub(r"@alfred\b", "", intent or "", flags=re.I).strip(" .,:;\"'")
    return text[:200]


def looks_like_setup_board_command(intent: str) -> bool:
    """True for `@alfred setup board`, not `create task for … board …`."""
    text = (intent or "").strip()
    if not text or looks_like_slack_board_create(text):
        return False
    return bool(_SETUP_BOARD_RE.search(text))


def extract_setup_board_custom_name(intent: str) -> str:
    match = _SETUP_BOARD_RE.search(intent or "")
    return (match.group(1) or "").strip() if match else ""


_WHERE_TASK_RE = re.compile(
    r"\bwhere\b.{0,24}\b(?:is|are|did|was)\b.{0,24}\b(?:the\s+)?(?:task|it|ticket)\b"
    r"|\bwhere\b.{0,20}\b(?:task|ticket)\b.{0,20}\b(?:created|go|land)\b",
    re.I,
)


def looks_like_board_where_question(intent: str) -> bool:
    return bool(_WHERE_TASK_RE.search(intent or ""))


def looks_like_slack_board_update(intent: str) -> bool:
    text = (intent or "").strip()
    if not text or looks_like_slack_board_create(text):
        return False
    if re.search(r"\b(?:display\s*)?(?:id\s*)?prefix\b", text, re.I):
        return False
    if _ASSIGN_RE.search(text) and re.search(
        r"\bassign\b.{0,16}\b(?:it|this|that|the)\b.{0,12}\bto\b", text, re.I
    ):
        return True
    if _BOARD_INLINE_STATUS_RE.search(text):
        return True
    if re.search(r"\bslack\s+board\b", text, re.I) and _TICKET_REF_RE.search(text):
        return True
    if _SEVERITY_ASSIGN_RE.search(text) and (
        _TICKET_REF_RE.search(text)
        or re.search(r"\b(?:this|the|that|last)\s+(?:task|ticket)\b", text, re.I)
    ):
        return True
    if not (_UPDATE_STATUS_RE.search(text) or _ASSIGN_RE.search(text)):
        return False
    if _TICKET_REF_RE.search(text):
        return True
    if re.search(r"\b(?:this|the|that|last)\s+(?:task|ticket)\b", text, re.I):
        return True
    return bool(re.search(r"\b(?:task|ticket)\b", text, re.I))


def resolve_ticket_ref(intent: str, *, session_metadata: dict[str, Any] | None = None) -> str:
    """Resolve TS-/Rec id from message or recent session task."""
    ref = extract_ticket_ref(intent)
    if ref:
        return ref
    last = dict((session_metadata or {}).get("last_board_task") or {})
    return str(last.get("display_id") or last.get("record_id") or "")


def humanize_slack_mentions_in_text(text: str, mention_labels: dict[str, str] | None = None) -> str:
    """Replace `<@U123|Name>` with `@Name` so thread context keeps who was tagged."""
    from backend.integrations.slack.sanitize import _MENTION_RE

    labels = mention_labels or {}

    def _repl(match: re.Match[str]) -> str:
        uid = match.group(1)
        name = (match.group(2) or labels.get(uid) or uid).strip()
        return f"@{name} "

    return _MENTION_RE.sub(_repl, text or "")


def format_board_thread_messages(
    messages: list[dict],
    *,
    mention_labels: dict[str, str] | None = None,
) -> str:
    """Thread text for board drafting — preserve @mentions instead of stripping them."""
    from backend.formatting.slack_messages import format_slack_ts, _message_author
    from backend.integrations.slack.sanitize import extract_slack_mention_labels

    labels = dict(mention_labels or {})
    lines: list[str] = []
    for index, message in enumerate(messages, start=1):
        raw = str(message.get("text") or "").strip()
        if not raw:
            continue
        labels.update(extract_slack_mention_labels(raw))
        body = humanize_slack_mentions_in_text(raw, labels).strip()
        if not body:
            continue
        author = _message_author(message, user_names=labels)
        when = format_slack_ts(message.get("ts") or "")
        lines.append(f"[{index}] {when} | {author}: {body}")
    return "\n".join(lines)


def infer_thread_action_assignee_from_messages(
    messages: list[dict],
    *,
    bot_user_id: str = "",
) -> str:
    """Assignee from raw Slack messages — `<@Riya> please share …`."""
    bot = (bot_user_id or "").strip()
    for message in messages:
        text = str(message.get("text") or "")
        match = _THREAD_ACTION_ASSIGNEE_RE.search(text)
        if not match:
            continue
        uid = match.group(1).strip()
        if uid and uid != bot:
            return uid
    return ""


def infer_thread_action_assignee(
    *texts: str,
    bot_user_id: str = "",
) -> str:
    """Assignee from thread root — person @mentioned before please/share/do (e.g. '@Riya please share')."""
    combined = "\n".join(t for t in texts if (t or "").strip())
    if not combined:
        return ""
    bot = (bot_user_id or "").strip()
    for line in combined.splitlines():
        line = line.strip()
        if not line:
            continue
        match = _THREAD_ACTION_ASSIGNEE_RE.search(line)
        if not match:
            continue
        uid = match.group(1).strip()
        if uid and uid != bot:
            return uid
    return ""


def extract_board_create_assignee(
    raw_text: str,
    intent: str = "",
    *,
    bot_user_id: str = "",
    requester_user_id: str = "",
) -> str:
    """Assignee from create command — prefer explicit mention, then cc fallback."""
    raw = raw_text or ""
    for pattern in (_CREATE_ASSIGNEE_RE, _ASSIGN_TO_RE):
        match = pattern.search(raw)
        if match:
            uid = match.group(1).strip()
            if uid and uid != bot_user_id:
                return uid

    from backend.integrations.slack.sanitize import extract_slack_user_ids

    def _filter_ids(text: str) -> list[str]:
        return [
            uid
            for uid in extract_slack_user_ids(text)
            if uid and uid != bot_user_id and uid != requester_user_id
        ]

    # Fallback: cc'd people when no explicit assignee in the create command.
    cc_split = re.split(r"\bcc\s*:\s*", raw, maxsplit=1, flags=re.I)
    if len(cc_split) > 1:
        cc_part = cc_split[1]
        create_match = _CREATE_CMD_RE.search(cc_part)
        cc_scope = cc_part[: create_match.start()] if create_match else cc_part
        cc_ids = _filter_ids(cc_scope)
        if cc_ids:
            return cc_ids[-1]

    user_ids = _filter_ids(raw)
    return user_ids[-1] if user_ids else ""


def references_thread_context(intent: str) -> bool:
    return bool(_ABOVE_RE.search(intent or ""))


def looks_like_batch_board_create(intent: str) -> bool:
    """True when the user asked to create a task for each listed item."""
    text = intent or ""
    if _BATCH_CREATE_RE.search(text):
        return True
    return bool(_CREATE_TASK_RE.search(text) and len(extract_numbered_task_titles(text)) >= 2)


def is_batch_title_noise(title: str) -> bool:
    """True for Alfred confirmation/governance lines that look like list items."""
    cleaned = re.sub(r"[*`_]+", "", title or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;-")
    if not cleaned:
        return True
    if _BATCH_METADATA_LINE_RE.search(cleaned):
        return True
    if _CREATED_TASK_LINE_RE.search(cleaned):
        return True
    return bool(_BATCH_TITLE_NOISE_RE.search(cleaned))


def is_bot_message_for_batch_titles(message: dict, bot_user_id: str = "") -> bool:
    """Skip Alfred/bot posts when harvesting numbered titles from a thread."""
    bot = (bot_user_id or "").strip()
    user = str(message.get("user") or "").strip()
    if bot and user == bot:
        return True
    if message.get("bot_id"):
        return True
    return "alfred" in str(message.get("username") or "").lower()


def extract_numbered_task_titles(*texts: str) -> list[str]:
    """Parse numbered or bulleted lines into distinct Slack List titles."""
    seen: set[str] = set()
    titles: list[str] = []
    for text in texts:
        for raw_line in (text or "").splitlines():
            match = _NUMBERED_ITEM_RE.match(raw_line)
            if not match:
                continue
            title = match.group(1).strip(" .,:;-")
            title = re.sub(r"^<@[^>]+>\s*", "", title).strip(" .,:;-")
            if not title or is_weak_board_task_title(title) or is_batch_title_noise(title):
                continue
            if _CREATE_COMMAND_LINE_RE.search(title) and len(title) < 80:
                continue
            key = re.sub(r"\s+", " ", title.lower())
            if key in seen:
                continue
            seen.add(key)
            titles.append(title[:200])
    return titles


def extract_batch_board_task_titles(
    request_text: str,
    *,
    thread_text: str = "",
) -> list[str]:
    """Titles for a batch create — prefer the current message when it already lists items.

    Thread bullets are only used for 'all the above' / similar, when the command
    itself has no numbered or bulleted list. That keeps Alfred's own confirmation
    and governance replies from becoming extra tasks.
    """
    from_request = extract_numbered_task_titles(request_text)
    if len(from_request) >= 2:
        return from_request
    if not (thread_text or "").strip():
        return from_request
    return extract_numbered_task_titles(request_text, thread_text)


def extract_ticket_ref(intent: str) -> str:
    match = _TICKET_REF_RE.search(intent or "")
    return match.group(1) if match else ""


def extract_task_title(intent: str) -> str:
    text = strip_list_id_override((intent or "").strip())

    def _clean_title(raw: str) -> str:
        title = raw.strip(" .,:;\"'?!")
        title = re.sub(r"\s+for\s+(the\s+)?above\s*$", "", title, flags=re.I).strip(" ?!")
        title = re.sub(r"\s+for\s+(the\s+)?same\s*$", "", title, flags=re.I).strip()
        title = strip_list_id_override(title)
        if is_weak_board_task_title(title):
            return ""
        return title[:200]

    match = _TITLE_FOR_RE.search(text)
    if match:
        title = _clean_title(match.group(1))
        if title:
            return title
    on_match = _TITLE_ON_RE.search(text)
    if on_match:
        title = _clean_title(on_match.group(1))
        if title:
            return title
    to_match = _TITLE_TO_RE.search(text)
    if to_match:
        title = _clean_title(to_match.group(1))
        if title:
            return title
    sep_match = _TITLE_SEP_RE.search(text)
    if sep_match:
        title = _clean_title(sep_match.group(1))
        if title:
            return title
    quoted = re.search(r"['\"]([^'\"]{3,200})['\"]", text)
    if quoted:
        return quoted.group(1).strip()
    for_match = re.search(
        r"\b(?:task|ticket)\b.{0,10}\bfor\b\s+(.+?)(?:\s+for\s+(?:the\s+)?above|\s*$)",
        text,
        re.I,
    )
    if for_match:
        title = _clean_title(for_match.group(1))
        if title:
            return title
    return ""


def extract_status_target(intent: str) -> str:
    text = (intent or "").lower()
    for label in ("not picked", "in progress", "review", "done"):
        if label in text:
            return label.title() if label != "in progress" else "In progress"
    move = re.search(r"\bto\s+([a-z][a-z\s-]{2,30})\b", text, re.I)
    if move:
        return move.group(1).strip().title()
    return ""


def extract_severity_target(intent: str) -> str:
    text = (intent or "").lower()
    for label in ("high", "medium", "low"):
        if re.search(rf"\b(?:severity|priority)\b.{{0,24}}\b{label}\b", text):
            return normalize_board_severity(label)
        if re.search(rf"\b{label}\b.{{0,24}}\b(?:severity|priority)\b", text):
            return normalize_board_severity(label)
    for level in ("p0", "p1", "p2", "p3"):
        if re.search(rf"\b(?:severity|priority)\b.{{0,12}}\b{level}\b", text):
            return normalize_board_severity(level)
        if level in text:
            return normalize_board_severity(level)
    return ""


def extract_title_from_summary(description: str) -> str:
    """Use Summary: line from structured ticket details as a task title fallback."""
    for line in (description or "").splitlines():
        match = re.match(r"^Summary:\s*(.+)$", line.strip(), re.I)
        if match:
            title = match.group(1).strip()[:200]
            if title and not is_weak_board_task_title(title):
                return title
    return ""


def build_board_mention_map(
    client: Any,
    task: Task,
    messages: list[dict],
) -> dict[str, str]:
    """Resolve Slack user ids to display names for board task drafting."""
    from backend.integrations.slack.sanitize import extract_slack_mention_labels, extract_slack_user_ids
    from backend.integrations.slack.users import SlackUserResolver, collect_message_user_ids

    user_ids = collect_message_user_ids(messages)
    user_ids.update(extract_slack_user_ids(task.raw_text or ""))
    if task.user_id:
        user_ids.add(task.user_id)
    labels: dict[str, str] = {}
    if client and user_ids:
        labels.update(SlackUserResolver(client).resolve_many(user_ids))
    for msg in messages:
        labels.update(extract_slack_mention_labels(str(msg.get("text") or "")))
    labels.update(extract_slack_mention_labels(task.raw_text or ""))
    return labels


def build_thread_description(messages_text: str, *, max_chars: int = 6000) -> str:
    """Legacy raw thread dump — prefer build_board_task_details."""
    return build_board_task_details(messages_text=messages_text, max_chars=max_chars)


def extract_comment_text(intent: str) -> str:
    text = intent or ""
    for pattern in (
        r"\bcomment(?:\s+on|\s+to|\s+in)?\s*(?:task|ticket)?\s*[:—-]\s*(.+)$",
        r"\bsaying\s+(.+)$",
        r"\bwith\s+(?:note|message)\s+(.+)$",
    ):
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1).strip()[:2000]
    return ""
