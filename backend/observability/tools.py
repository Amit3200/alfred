"""Tool name → category mapping for observability (delegates to catalog)."""

from __future__ import annotations

from backend.tools.catalog import (
    AWS_TOOLS,
    GIT_TOOLS,
    GOOGLE_TOOLS,
    JIRA_TOOLS,
    SLACK_TOOLS,
    WEB_TOOLS,
    tool_category,
    tool_domain,
)

__all__ = [
    "AWS_TOOLS",
    "GIT_TOOLS",
    "GOOGLE_TOOLS",
    "JIRA_TOOLS",
    "SLACK_TOOLS",
    "WEB_TOOLS",
    "tool_category",
    "tool_domain",
]
