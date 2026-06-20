"""Normalize assistant output for the admin UI (Markdown)."""

from __future__ import annotations

import re
from typing import Callable

_SLACK_LINK_RE = re.compile(r"<([^|>\s]+)\|([^>]+)>")
_SLACK_BOLD_RE = re.compile(r"(?<!\*)\*(?!\*)([^*\n]+?)(?<!\*)\*(?!\*)")
_REPO_LINE_RE = re.compile(r"^`([^`]+)`$")
_PR_BULLET_RE = re.compile(
    r"^[•\-]\s*(#\d+\s+.+?)(?:\s*[—–-]\s+(https://\S+))?\s*$",
)
_PR_PLAIN_RE = re.compile(
    r"^(#\d+\s+.+?)\s*[—–-]\s+(https://\S+)\s*$",
)
_FENCE_RE = re.compile(r"^```")


def format_for_ui(text: str) -> str:
    """Convert Slack-style mrkdwn leftovers into clean Markdown for the UI."""
    return _process_outside_fences(text, _apply_ui_formatting).strip()


def _apply_ui_formatting(text: str) -> str:
    text = _SLACK_LINK_RE.sub(r"[\2](\1)", text)
    text = _SLACK_BOLD_RE.sub(r"**\1**", text)

    lines: list[str] = []
    for line in text.split("\n"):
        for normalized in _normalize_line(line):
            lines.append(normalized)
    return "\n".join(lines)


def _normalize_line(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped:
        return [""]

    if match := _REPO_LINE_RE.match(stripped):
        return ["", f"### {match.group(1)}"]

    if "•" in stripped:
        parts = [part.strip() for part in re.split(r"\s*•\s*", stripped) if part.strip()]
        if len(parts) > 1:
            out: list[str] = []
            for part in parts:
                out.extend(_normalize_line(part))
            return out

    if match := _PR_BULLET_RE.match(stripped):
        label = match.group(1).strip()
        url = match.group(2)
        if url:
            return [f"- [{label}]({url})"]
        return [f"- {label}"]

    if match := _PR_PLAIN_RE.match(stripped):
        return [f"- [{match.group(1).strip()}]({match.group(2)})"]

    return [line]


def _process_outside_fences(text: str, transform: Callable[[str], str]) -> str:
    lines = text.split("\n")
    output: list[str] = []
    in_fence = False
    chunk: list[str] = []

    def flush_chunk() -> None:
        nonlocal chunk
        if chunk:
            output.append(transform("\n".join(chunk)))
            chunk = []

    for line in lines:
        if _FENCE_RE.match(line.strip()):
            flush_chunk()
            in_fence = not in_fence
            output.append(line)
            continue
        if in_fence:
            output.append(line)
        else:
            chunk.append(line)

    flush_chunk()
    return "\n".join(output)
