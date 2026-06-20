"""Git API tools — list PRs, get PR details, list repos (no local clone)."""

from __future__ import annotations

from typing import Any

from backend.ai.base import ToolSchema
from backend.git.api import GitApiClient, resolve_repo_slug
from backend.models.config import AlfredConfig
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult

LIST_MY_PRS = ToolSchema(
    name="list_my_prs",
    description="List pull requests created by the authenticated Git user.",
    parameters={
        "type": "object",
        "properties": {
            "state": {
                "type": "string",
                "enum": ["open", "closed", "all"],
                "description": "PR state filter (default open).",
            },
        },
        "required": [],
    },
)

LIST_PRS = ToolSchema(
    name="list_prs",
    description="List pull requests for a repository (owner/name).",
    parameters={
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository slug, e.g. myorg/backend.",
            },
            "state": {
                "type": "string",
                "enum": ["open", "closed", "all"],
                "description": "PR state filter (default open).",
            },
        },
        "required": ["repo"],
    },
)

GET_PR = ToolSchema(
    name="get_pr",
    description="Get details for a single pull request by number.",
    parameters={
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository slug, e.g. myorg/backend.",
            },
            "number": {
                "type": "integer",
                "description": "Pull request number.",
            },
        },
        "required": ["repo", "number"],
    },
)

LIST_REPOS = ToolSchema(
    name="list_repos",
    description="List configured or accessible Git repositories.",
    parameters={"type": "object", "properties": {}, "required": []},
)


def build_git_tool_registry(config: AlfredConfig) -> ToolRegistry:
    client = GitApiClient.from_alfred_config(config)
    registry = ToolRegistry()
    registry.clear_results()
    registry.git_config = config.git

    def list_my_prs_handler(args: dict[str, Any]) -> ToolResult:
        state = str(args.get("state") or "open")
        prs = client.list_my_prs(state=state)
        return ToolResult.pr_list(prs, state=state)

    def list_prs_handler(args: dict[str, Any]) -> ToolResult:
        repo = str(args.get("repo") or "").strip()
        if not repo:
            return ToolResult.error("repo is required (owner/name).")
        try:
            repo = resolve_repo_slug(repo, config.git)
        except ValueError as exc:
            return ToolResult.error(str(exc))
        state = str(args.get("state") or "open")
        prs = client.list_prs(repo, state=state)
        return ToolResult.pr_list(prs, state=state)

    def get_pr_handler(args: dict[str, Any]) -> ToolResult:
        repo = str(args.get("repo") or "").strip()
        number = args.get("number")
        if not repo or number is None:
            return ToolResult.error("repo and number are required.")
        try:
            repo = resolve_repo_slug(repo, config.git)
        except ValueError as exc:
            return ToolResult.error(str(exc))
        data = client.get_pr(repo, int(number))
        return ToolResult.pr_detail(data)

    def list_repos_handler(_args: dict[str, Any]) -> ToolResult:
        repos = client.list_repos()
        return ToolResult.repo_list(repos)

    registry.register(LIST_MY_PRS, list_my_prs_handler)
    registry.register(LIST_PRS, list_prs_handler)
    registry.register(GET_PR, get_pr_handler)
    registry.register(LIST_REPOS, list_repos_handler)
    return registry
