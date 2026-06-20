"""Generic rules for when to fetch Slack history and refresh session context."""

from __future__ import annotations

# Skip channel fetch for identity / capability questions.
_IDENTITY_MARKERS = (
    "who are you",
    "what is alfred",
    "what are you",
    "what can you do",
    "introduce yourself",
)

# Re-fetch Slack history on follow-ups.
_REFRESH_MARKERS = (
    "try again",
    "can you try again",
    "look again",
    "check again",
    "tell me again",
    "say again",
    "this again",
    "one more time",
    "repeat that",
    "update",
    "recap",
)

_CORRECTION_MARKERS = (
    "oops",
    "i meant",
    "i mean",
    "actually",
    "no i meant",
    "not that",
    "wrong",
)

# User explicitly asks about channel-wide history.
_CHANNEL_MARKERS = (
    "in this channel",
    "not in thread",
    "outside this thread",
    "summarize this channel",
    "channel history",
)

# Summary / recap requests (channel or thread).
_SUMMARY_MARKERS = (
    "summarize",
    "summary",
    "takeaway",
    "takeaways",
    "take away",
)

# Time-bounded questions.
_TIME_MARKERS = (
    "yesterday",
    "today",
    "last week",
    "past week",
    "this week",
)

# Generic factual lookups in history (not domain-specific).
_LOOKUP_MARKERS = (
    "when was",
    "when did",
    "who acked",
    "who acknowledged",
    "who reacted",
    "last ",
    "latest",
    "most recent",
)


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in markers)


def is_identity_question(intent: str) -> bool:
    return _contains_any(intent, _IDENTITY_MARKERS)


def wants_channel_history(intent: str, *, in_existing_thread: bool) -> bool:
    """Decide whether to include channel messages in Slack context."""
    if is_identity_question(intent):
        return False
    if _contains_any(intent, _REFRESH_MARKERS + _CORRECTION_MARKERS):
        return True
    if _contains_any(intent, _CHANNEL_MARKERS + _SUMMARY_MARKERS + _TIME_MARKERS + _LOOKUP_MARKERS):
        return True
    return not in_existing_thread


def needs_context_refresh(intent: str, *, has_session: bool) -> bool:
    """Re-attach Slack history on follow-ups that need fresh facts."""
    if not has_session:
        return True
    if _contains_any(
        intent,
        _REFRESH_MARKERS
        + _CORRECTION_MARKERS
        + _CHANNEL_MARKERS
        + _SUMMARY_MARKERS
        + _TIME_MARKERS
        + _LOOKUP_MARKERS,
    ):
        return True
    return False


def omit_assistant_session_history(intent: str, *, include_context: bool) -> bool:
    """Drop prior assistant turns when re-answering from fresh Slack facts."""
    if not include_context:
        return False
    if _contains_any(intent, _LOOKUP_MARKERS + _REFRESH_MARKERS + _CORRECTION_MARKERS):
        return True
    return False
