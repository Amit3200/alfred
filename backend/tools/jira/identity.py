"""Identity lookup tools (Slack ↔ JIRA mapping)."""

from __future__ import annotations

from typing import Any

from backend.ai.base import ToolSchema
from backend.integrations.identity.user_identity import (
    build_workspace_identity_map,
    lookup_user_identity,
)
from backend.tools.base.tool import BaseTool, ToolContext
from backend.tools.jira.schemas import BUILD_WORKSPACE_IDENTITY_MAP, LOOKUP_USER_IDENTITY
from backend.tools.result import ToolResult


class LookupUserIdentityTool(BaseTool):
    name = "lookup_user_identity"
    capability = "identity.lookup"
    operation = "lookup"
    domain = "identity"

    def schema(self) -> ToolSchema:
        return LOOKUP_USER_IDENTITY

    def run(self, ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        data = lookup_user_identity(
            ctx.config,
            slack_user_id=str(arguments.get("slack_user_id") or ""),
            query=str(arguments.get("query") or ""),
            targets=arguments.get("targets"),
        )
        if data.get("error"):
            return ToolResult.error(str(data["error"]))
        return ToolResult(kind="user_identity", data=data)


class BuildWorkspaceIdentityMapTool(BaseTool):
    name = "build_workspace_identity_map"
    capability = "identity.map"
    operation = "map"
    domain = "identity"

    def schema(self) -> ToolSchema:
        return BUILD_WORKSPACE_IDENTITY_MAP

    def run(self, ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        data = build_workspace_identity_map(
            ctx.config,
            include_github=bool(arguments.get("include_github", True)),
        )
        if data.get("error"):
            return ToolResult.error(str(data["error"]))
        return ToolResult(kind="user_identity", data=data)
