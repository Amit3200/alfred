"""Normalize JIRA board titles to project keys."""

from __future__ import annotations

import re

from backend.models.config import JiraConfig

_BOARD_SUFFIX_RE = re.compile(r"\s+boards?$", re.I)
_FILLER_RE = re.compile(r"\b(?:jira|the|on|in)\b", re.I)
_PERSONA_PROJECT_RE = re.compile(
    r"project(?:\s+key)?\s*[=:`\s]+\s*`?([A-Za-z][A-Za-z0-9_-]{1,15})`?",
    re.I,
)
_PERSONA_PROJECT_STOP = frozenset(
    {"the", "this", "that", "your", "our", "and", "for", "from", "with", "key", "jira"}
)


def resolve_project_alias(text: str, config: JiraConfig) -> str | None:
    """Resolve board/display name phrases to project keys via config.project_aliases."""
    lower = (text or "").lower()
    if not lower or not config.project_aliases:
        return None
    for alias, project_key in sorted(
        config.project_aliases.items(),
        key=lambda item: -len(str(item[0])),
    ):
        needle = str(alias).strip().lower()
        key = str(project_key).strip().upper()
        if needle and key and needle in lower:
            return key
    return None


def normalize_jira_project_key(raw: str, config: JiraConfig | None = None) -> str:
    """Map board titles like 'JIRA Tech Board' to a project key (TECH)."""
    text = (raw or "").strip()
    if not text:
        return ""
    if config is not None:
        aliased = resolve_project_alias(text, config)
        if aliased:
            return aliased
    cleaned = _FILLER_RE.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = _BOARD_SUFFIX_RE.sub("", cleaned).strip()
    if config is not None and cleaned:
        aliased = resolve_project_alias(cleaned, config) or resolve_project_alias(
            f"{cleaned} board", config
        )
        if aliased:
            return aliased
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", cleaned or ""):
        return cleaned.replace("_", "-").upper()
    tokens = [tok for tok in re.split(r"[^A-Za-z0-9]+", cleaned) if tok]
    for tok in reversed(tokens):
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9]+", tok):
            return tok.upper()
    return text.strip().upper()


def project_key_from_persona(persona: str, config: JiraConfig | None = None) -> str:
    """Extract a JIRA project key from channel persona text (e.g. project=TECH)."""
    text = (persona or "").strip()
    if not text:
        return ""
    match = _PERSONA_PROJECT_RE.search(text)
    if not match:
        return ""
    token = str(match.group(1) or "").strip()
    if not token or token.lower() in _PERSONA_PROJECT_STOP:
        return ""
    return normalize_jira_project_key(token, config)
