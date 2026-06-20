"""Strip internal prompt scaffold labels from model output."""

from __future__ import annotations

import re

# Labels the model sometimes copies from instructions — remove line prefixes only.
_SCAFFOLD_LINE_RE = re.compile(
    r"^(?:Lead line|Body|Context Recap|Summary of Current State|Next [Ss]teps|Note)\s*:?\s*",
    re.MULTILINE,
)

# Standalone scaffold header lines with no content.
_SCAFFOLD_ONLY_LINE_RE = re.compile(
    r"^(?:Lead line|Body|Context Recap|Summary of Current State|Next [Ss]teps|Note)\s*:?\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def clean_response_scaffold(text: str) -> str:
    if not text:
        return text
    cleaned = _SCAFFOLD_LINE_RE.sub("", text)
    cleaned = _SCAFFOLD_ONLY_LINE_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
