"""Generic rules for when to fetch Slack history and refresh session context."""

from __future__ import annotations

from backend.formatting.slack_lists import wants_slack_list_enrichment

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
    if wants_slack_list_enrichment(intent):
        return True
    if _contains_any(intent, _REFRESH_MARKERS + _CORRECTION_MARKERS):
        return True
    if _contains_any(intent, _CHANNEL_MARKERS + _SUMMARY_MARKERS + _TIME_MARKERS + _LOOKUP_MARKERS):
        return True
    return not in_existing_thread


def needs_context_refresh(intent: str, *, has_session: bool) -> bool:
    """Re-attach Slack history on follow-ups that need fresh facts."""
    if not has_session:
        return True
    if wants_slack_list_enrichment(intent):
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


def omit_assistant_session_history(
    intent: str,
    *,
    include_context: bool,
    pr_review_active: bool = False,
) -> bool:
    """Drop prior assistant turns when re-answering from fresh Slack facts."""
    if not include_context:
        return False
    if pr_review_active:
        return False
    if _contains_any(intent, _LOOKUP_MARKERS + _REFRESH_MARKERS + _CORRECTION_MARKERS):
        return True
    return False


import re

_TRACEBACK_RE = re.compile(
    r"(Traceback \(most recent call last\):.*?(?:\r?\n.*?)+?)(?=\n\S|\Z)",
    re.DOTALL | re.IGNORECASE,
)

_URL_RE = re.compile(r"https?://[^\s>#]+", re.IGNORECASE)


def prune_context(text: str) -> str:
    """Strip out or truncate long stack traces and URLs from context to reduce token footprint."""
    if not text:
        return text

    # 1. Truncate long tracebacks
    def replace_tb(match: re.Match) -> str:
        tb = match.group(1).strip()
        lines = tb.splitlines()
        if len(lines) > 8:
            return (
                "\n".join(lines[:3])
                + "\n... [Stack trace truncated for LLM readability] ...\n"
                + "\n".join(lines[-3:])
            )
        return tb

    pruned = _TRACEBACK_RE.sub(replace_tb, text)

    # 2. Shorten excessively long URLs
    def replace_url(match: re.Match) -> str:
        url = match.group(0)
        if len(url) > 150:
            parts = url.split("?", 1)
            base = parts[0]
            if len(base) > 100:
                base = base[:100] + "..."
            query = f"?{parts[1][:30]}..." if len(parts) > 1 else ""
            return f"{base}{query} [URL truncated]"
        return url

    pruned = _URL_RE.sub(replace_url, pruned)

    return pruned
