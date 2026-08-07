"""Parse Slack board task intents and thread context."""

from __future__ import annotations

import re
from typing import Any

_CREATE_TASK_RE = re.compile(
    r"\b(?:create|add|open|file|raise|log)\b.{0,20}\b(?:task|ticket|item|bug)\b",
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
_TICKET_REF_RE = re.compile(
    r"\b((?:TS|BUG|TK|T)-\d+|Rec[A-Za-z0-9]+)\b",
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
_FOLLOWUP_STATUS_RE = re.compile(
    r"\b(?:yes|yep|yeah|ok(?:ay)?)\b.{0,40}\b(?:created|done|there|it)\b"
    r"|\b(?:is|was)\s+it\s+created\b"
    r"|\b(?:did\s+(?:you|that|it)|has\s+it)\s+(?:create|work)\b"
    r"|\bcreated\s*\?\s*$",
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
    if looks_like_slack_board_create(intent):
        return False
    text = (intent or "").strip()
    if not text:
        return False
    if not _FOLLOWUP_STATUS_RE.search(text):
        return False
    combined = "\n".join([*session_turns[-8:], thread_context or "", text]).lower()
    return sum(1 for marker in _BOARD_SESSION_MARKERS if marker in combined) >= 1


def looks_like_slack_board_create(intent: str) -> bool:
    return bool(_CREATE_TASK_RE.search(intent or ""))


def looks_like_slack_board_update(intent: str) -> bool:
    text = (intent or "").strip()
    if not text or looks_like_slack_board_create(text):
        return False
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


def references_thread_context(intent: str) -> bool:
    return bool(_ABOVE_RE.search(intent or ""))


def extract_ticket_ref(intent: str) -> str:
    match = _TICKET_REF_RE.search(intent or "")
    return match.group(1) if match else ""


def extract_task_title(intent: str) -> str:
    text = strip_list_id_override((intent or "").strip())

    def _clean_title(raw: str) -> str:
        title = raw.strip(" .,:;\"'")
        title = re.sub(r"\s+for\s+(the\s+)?above\s*$", "", title, flags=re.I).strip()
        title = strip_list_id_override(title)
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
    quoted = re.search(r"['\"]([^'\"]{3,200})['\"]", text)
    if quoted:
        return quoted.group(1).strip()
    for_match = re.search(
        r"\b(?:task|ticket)\b.{0,10}\bfor\b\s+(.+?)(?:\s+for\s+(?:the\s+)?above|\s*$)",
        text,
        re.I,
    )
    if for_match:
        return for_match.group(1).strip(" .,:;")[:200]
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


def build_thread_description(messages_text: str, *, max_chars: int = 6000) -> str:
    body = (messages_text or "").strip()
    if not body:
        return "Created from Slack thread (no messages captured)."
    if len(body) > max_chars:
        return body[: max_chars - 20] + "\n… (truncated)"
    return body
