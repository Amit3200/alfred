"""JIRA tool bundle — class-based registration."""

from __future__ import annotations

from backend.tools.base.bundle import ToolBundle
from backend.tools.base.tool import BaseTool
from backend.tools.jira.identity import BuildWorkspaceIdentityMapTool, LookupUserIdentityTool
from backend.tools.jira.read import JiraGetIssueTool, JiraListIssuesTool, JiraSearchTool
from backend.tools.jira.write import (
    JiraAddCommentAliasTool,
    JiraAddCommentTool,
    JiraAssignIssueTool,
    JiraCreateIssueTool,
    JiraLinkIssueTool,
    JiraTransitionIssueTool,
    JiraUpdateIssueTool,
)


class JiraToolBundle(ToolBundle):
    capability_prefix = "jira"

    def tools(self) -> list[BaseTool]:
        return [
            JiraGetIssueTool(),
            JiraListIssuesTool(),
            JiraSearchTool(),
            JiraCreateIssueTool(),
            JiraAssignIssueTool(),
            JiraTransitionIssueTool(),
            JiraAddCommentTool(),
            JiraAddCommentAliasTool(),
            JiraUpdateIssueTool(),
            JiraLinkIssueTool(),
        ]


class IdentityToolBundle(ToolBundle):
    capability_prefix = "identity"

    def tools(self) -> list[BaseTool]:
        return [
            LookupUserIdentityTool(),
            BuildWorkspaceIdentityMapTool(),
        ]
