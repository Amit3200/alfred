"""Check which playbook tools are registered for the current Alfred config."""

from __future__ import annotations

from backend.models.config import AlfredConfig
from backend.tools.catalog import (
    ALL_KNOWN_TOOLS,
    AWS_TOOLS,
    COMPANY_SCRIPT_TOOLS,
    GIT_API_TOOLS,
    GIT_LOCAL_TOOLS,
    GIT_WRITE_TOOLS,
    GOOGLE_TOOLS,
    GRAPHIFY_TOOLS,
    JIRA_MODULE_TOOLS,
    REPO_DOC_TOOLS,
    SCHEDULE_TOOLS,
    WEB_TOOLS,
)


def configured_tool_names(config: AlfredConfig) -> frozenset[str]:
    """Tool names that would register when building the tool registry."""
    names: set[str] = set()

    if config.git.enabled:
        names |= GIT_API_TOOLS | GIT_LOCAL_TOOLS | GRAPHIFY_TOOLS
        if config.git.write_enabled:
            names |= GIT_WRITE_TOOLS
        if config.repo_knowledge.enabled:
            names |= REPO_DOC_TOOLS

    if config.jira.enabled:
        names |= JIRA_MODULE_TOOLS

    if config.aws.enabled:
        names |= AWS_TOOLS

    if config.google.enabled:
        names |= GOOGLE_TOOLS

    if config.web_search.enabled:
        names |= WEB_TOOLS

    names |= COMPANY_SCRIPT_TOOLS | SCHEDULE_TOOLS
    return frozenset(names)


def resolvable_playbook_tools(
    allowed_tools: list[str],
    config: AlfredConfig,
) -> tuple[list[str], list[str], list[str]]:
    """Return (available, unknown, disabled) tool names for a playbook allowlist."""
    if not allowed_tools:
        return [], [], []

    available_names = configured_tool_names(config)
    available: list[str] = []
    unknown: list[str] = []
    disabled: list[str] = []

    for name in allowed_tools:
        if name not in ALL_KNOWN_TOOLS:
            unknown.append(name)
            continue
        if name in available_names:
            available.append(name)
        else:
            disabled.append(name)

    return available, unknown, disabled


def playbook_has_runnable_tools(allowed_tools: list[str], config: AlfredConfig) -> bool:
    """True when at least one allowed tool is known and enabled."""
    if not allowed_tools:
        return True
    available, _, _ = resolvable_playbook_tools(allowed_tools, config)
    return bool(available)
