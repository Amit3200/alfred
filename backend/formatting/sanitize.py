from __future__ import annotations

import re

# RegExes for sanitizing/cleaning
_MENTION_RE = re.compile(r"<@([A-Z0-9]+)(?:\|([^>]+))?>\s*")
_ALFRED_PREFIX_RE = re.compile(r"^@?alfred[,:]?\s+", re.IGNORECASE)

_SCAFFOLD_LINE_RE = re.compile(
    r"^(?:Lead line|Body|Context Recap|Summary of Current State|Next [Ss]teps|Note)\s*:?\s*",
    re.MULTILINE,
)
_SCAFFOLD_ONLY_LINE_RE = re.compile(
    r"^(?:Lead line|Body|Context Recap|Summary of Current State|Next [Ss]teps|Note)\s*:?\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def clean_slack_text(raw_text: str) -> str:
    """Strip Slack `<@U...>` mentions and leading `@alfred` triggers."""
    text = _MENTION_RE.sub("", raw_text or "").strip()
    text = _ALFRED_PREFIX_RE.sub("", text).strip()
    return text


def clean_response_scaffold(text: str) -> str:
    """Strip internal instruction headers and markdown tool scaffolds from assistant output."""
    if not text:
        return text
    from backend.routing.git.direct import looks_like_tool_json, strip_text_tool_markup
    cleaned = strip_text_tool_markup(text)
    if looks_like_tool_json(cleaned):
        cleaned = strip_text_tool_markup(cleaned)
    cleaned = _SCAFFOLD_LINE_RE.sub("", cleaned)
    cleaned = _SCAFFOLD_ONLY_LINE_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
