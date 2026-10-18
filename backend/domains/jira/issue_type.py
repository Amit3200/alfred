"""Resolve a JIRA create issue type, defaulting to Task when unsure."""

from __future__ import annotations

import re
from typing import Any

DEFAULT_JIRA_ISSUE_TYPE = "Task"

_EXPLICIT_TYPES = frozenset(
    {
        "task",
        "story",
        "epic",
        "bug",
        "sub-task",
        "subtask",
        "improvement",
        "new feature",
        "spike",
        "process",
    }
)
_UNCERTAIN_RE = re.compile(
    r"^(?:ticket|issue|item|board|tech[- ]?support|placeholder|tbd|n/?a|none|todo|"
    r"to be provided by user|optional details from user)$",
    re.I,
)


def resolve_jira_create_issue_type(
    raw: str,
    *,
    project: str = "",
    config: Any = None,
) -> str:
    """Return a concrete issue type name.

    Empty, placeholder, or generic words like ``ticket`` / ``issue`` fall back to
    ``jira.project_issue_types[project]`` when set, otherwise **Task**.
    """
    configured = _configured_type(project, config)
    kind = (raw or "").strip()
    if not kind or _UNCERTAIN_RE.match(kind) or kind.startswith("<"):
        return configured or DEFAULT_JIRA_ISSUE_TYPE
    if kind.lower() not in _EXPLICIT_TYPES and re.search(
        r"\b(?:board|jira|project|support)\b", kind, re.I
    ):
        return configured or DEFAULT_JIRA_ISSUE_TYPE
    return kind


def is_issuetype_error(message: str) -> bool:
    lower = (message or "").lower()
    return "issuetype" in lower and (
        "valid issue type" in lower or "specify a valid" in lower or "does not exist" in lower
    )


def _configured_type(project: str, config: Any) -> str:
    if not project or config is None:
        return ""
    jira = getattr(config, "jira", config)
    mapping = getattr(jira, "project_issue_types", None) or {}
    key = (project or "").strip()
    return str(mapping.get(key) or mapping.get(key.upper()) or "").strip()
