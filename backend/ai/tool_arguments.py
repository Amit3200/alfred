"""Parse model-emitted tool call JSON safely."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_SALVAGE_STRING_KEYS = (
    "project",
    "summary",
    "issue_type",
    "priority",
    "description",
    "issue_key",
    "jql",
    "repo",
    "query",
    "assignee",
    "reporter",
)


def parse_tool_call_arguments(raw: Any, *, tool_name: str = "") -> dict[str, Any]:
    """Best-effort parse of provider tool arguments; never raises JSONDecodeError."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}

    text = raw.strip()
    if not text:
        return {}

    for candidate in _argument_candidates(text):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    salvaged = _salvage_partial_tool_json(text)
    if salvaged:
        logger.warning(
            "Salvaged partial tool arguments for %s from malformed JSON (%d chars)",
            tool_name or "unknown",
            len(text),
        )
        return salvaged

    logger.warning(
        "Failed to parse tool call arguments for %s: %r",
        tool_name or "unknown",
        text[:240],
    )
    return {}


def _argument_candidates(text: str) -> list[str]:
    seen: set[str] = set()
    candidates: list[str] = []

    def add(value: str) -> None:
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            candidates.append(cleaned)

    add(text)
    add(_fix_malformed_tool_json(text))

    if text.count('"') % 2 == 1:
        add(text + '"')
        add(_fix_malformed_tool_json(text + '"'))

    if not text.rstrip().endswith("}"):
        add(text.rstrip() + "}")
        add(_fix_malformed_tool_json(text.rstrip() + "}"))

    if text.count('"') % 2 == 1 and not text.rstrip().endswith("}"):
        add(text.rstrip() + '"}')
        add(_fix_malformed_tool_json(text.rstrip() + '"}'))

    return candidates


def _fix_malformed_tool_json(text: str) -> str:
    """Best-effort repair for models that truncate or omit JSON syntax."""
    fixed = text.strip()
    fixed = re.sub(r'"parameters"\s*\{', '"parameters": {', fixed)
    fixed = re.sub(r'"parameters\s*\{', '"parameters": {', fixed)
    fixed = re.sub(r'"(\w+)""\s*:', r'"\1":', fixed)
    fixed = re.sub(r':\s*""([^"]+)""', r': "\1"', fixed)
    if fixed.count("{") > fixed.count("}"):
        fixed += "}" * (fixed.count("{") - fixed.count("}"))
    if fixed.count('"') % 2 == 1:
        fixed += '"'
    return fixed


def _salvage_partial_tool_json(text: str) -> dict[str, Any]:
    """Extract string fields from truncated tool JSON (common on long descriptions)."""
    result: dict[str, Any] = {}
    for key in _SALVAGE_STRING_KEYS:
        match = re.search(rf'"{re.escape(key)}"\s*:\s*"((?:[^"\\]|\\.)*)', text)
        if match:
            value = match.group(1)
            try:
                result[key] = bytes(value, "utf-8").decode("unicode_escape")
            except UnicodeDecodeError:
                result[key] = value
    return result
