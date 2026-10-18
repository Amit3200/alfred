"""Register class-based JIRA and identity tools."""

from __future__ import annotations

from backend.integrations.jira.api import JiraApiClient
from backend.models.config import AlfredConfig
from backend.tools.jira.bundle import IdentityToolBundle, JiraToolBundle
from backend.tools.jira.schemas import (
    ADD_JIRA_COMMENT,
    BUILD_WORKSPACE_IDENTITY_MAP,
    GET_JIRA_ISSUE,
    JIRA_ADD_COMMENT,
    JIRA_ASSIGN_ISSUE,
    JIRA_CREATE_ISSUE,
    JIRA_SEARCH,
    JIRA_UPDATE_ISSUE,
    LINK_JIRA_ISSUE,
    LIST_JIRA_ISSUES,
    LOOKUP_USER_IDENTITY,
    TRANSITION_JIRA_ISSUE,
)
from backend.tools.registry import ToolRegistry

__all__ = [
    "register_jira_tools",
    "ADD_JIRA_COMMENT",
    "BUILD_WORKSPACE_IDENTITY_MAP",
    "GET_JIRA_ISSUE",
    "JIRA_ADD_COMMENT",
    "JIRA_ASSIGN_ISSUE",
    "JIRA_CREATE_ISSUE",
    "JIRA_SEARCH",
    "JIRA_UPDATE_ISSUE",
    "LINK_JIRA_ISSUE",
    "LIST_JIRA_ISSUES",
    "LOOKUP_USER_IDENTITY",
    "TRANSITION_JIRA_ISSUE",
]


def register_jira_tools(registry: ToolRegistry, config: AlfredConfig) -> None:
    registry.alfred_config = config
    if not config.jira.enabled and not config.slack.enabled:
        return

    IdentityToolBundle().register(registry)

    if not config.jira.enabled:
        return

    try:
        JiraApiClient.from_alfred_config(config)
    except RuntimeError:
        return

    JiraToolBundle().register(registry)
