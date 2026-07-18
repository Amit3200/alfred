"""Git API tools — list PRs, get PR details, list repos (no local clone)."""

from __future__ import annotations
from backend.tools.catalog import (
    AWS_TOOLS,
    COMPANY_SCRIPT_TOOLS,
    GIT_API_TOOLS,
    GIT_LOCAL_TOOLS,
    GIT_TOOLS,
    GIT_WRITE_TOOLS,
    GOOGLE_TOOLS,
    GRAPHIFY_TOOLS,
    JIRA_MODULE_TOOLS,
    SCHEDULE_TOOLS,
    WEB_TOOLS,
)
from backend.tools.git_local import register_local_git_tools
from backend.tools.git_write import register_git_write_tools
from backend.tools.graphify_tool import register_graphify_tools
from backend.tools.jira_tool import register_jira_tools
from backend.tools.aws_tool import register_aws_tools
from backend.tools.google_tool import register_google_tools
from backend.tools.selection import wants_module, wants_tool

from pathlib import Path
from typing import Any

from backend.ai.base import ToolSchema
from backend.integrations.git.api import GitApiClient, resolve_repo_slug
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

GET_PR_CHANGES = ToolSchema(
    name="get_pr_changes",
    description="List files changed in a pull request with diff patches.",
    parameters={
        "type": "object",
        "properties": {
            "repo": {"type": "string", "description": "Repository slug, e.g. myorg/backend."},
            "number": {"type": "integer", "description": "Pull request number."},
        },
        "required": ["repo", "number"],
    },
)

LIST_REPOS = ToolSchema(
    name="list_repos",
    description="List configured or accessible Git repositories.",
    parameters={"type": "object", "properties": {}, "required": []},
)


def build_git_tool_registry(
    config: AlfredConfig,
    *,
    workspace_id: str | None = None,
    data_dir: Path | None = None,
    allowed_tools: list[str] | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    registry.clear_results()
    registry.set_registration_filter(allowed_tools)
    registry.git_config = config.git
    registry.workspace_id = workspace_id
    registry.data_dir = data_dir

    allowed = registry._registration_filter

    if config.git.enabled and wants_module(GIT_TOOLS, allowed):
        if wants_module(GIT_API_TOOLS, allowed):
            client = GitApiClient.from_alfred_config(config)

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

            def get_pr_changes_handler(args: dict[str, Any]) -> ToolResult:
                repo = str(args.get("repo") or "").strip()
                number = args.get("number")
                if not repo or number is None:
                    return ToolResult.error("repo and number are required.")
                try:
                    repo = resolve_repo_slug(repo, config.git)
                except ValueError as exc:
                    return ToolResult.error(str(exc))
                detail = client.get_pr(repo, int(number))
                files = client.get_pr_files(repo, int(number))
                return ToolResult(
                    kind="pr_changes",
                    data={
                        "repo": repo,
                        "number": int(number),
                        "head": detail.get("head"),
                        "base": detail.get("base"),
                        "files": files,
                    },
                )

            def list_repos_handler(_args: dict[str, Any]) -> ToolResult:
                repos = client.list_repos()
                return ToolResult.repo_list(repos)

            if wants_tool("list_my_prs", allowed):
                registry.register(LIST_MY_PRS, list_my_prs_handler)
            if wants_tool("list_prs", allowed):
                registry.register(LIST_PRS, list_prs_handler)
            if wants_tool("get_pr", allowed):
                registry.register(GET_PR, get_pr_handler)
            if wants_tool("get_pr_changes", allowed):
                registry.register(GET_PR_CHANGES, get_pr_changes_handler)
            if wants_tool("list_repos", allowed):
                registry.register(LIST_REPOS, list_repos_handler)

        if data_dir is not None:
            if wants_module(GIT_LOCAL_TOOLS, allowed):
                register_local_git_tools(registry, config=config, data_dir=Path(data_dir))
            if config.git.write_enabled and wants_module(GIT_WRITE_TOOLS, allowed):
                register_git_write_tools(registry, config=config, data_dir=Path(data_dir))
            if wants_module(GRAPHIFY_TOOLS, allowed):
                register_graphify_tools(registry, config=config, data_dir=Path(data_dir))

    if wants_module(JIRA_MODULE_TOOLS, allowed):
        register_jira_tools(registry, config)

    if wants_module(AWS_TOOLS, allowed):
        register_aws_tools(registry, config)

    if wants_module(GOOGLE_TOOLS, allowed):
        register_google_tools(registry, config)

    if wants_module(WEB_TOOLS, allowed):
        from backend.tools.web_search_tool import register_web_search_tools

        register_web_search_tools(registry, config)

    if wants_module(SCHEDULE_TOOLS, allowed):
        from backend.tools.schedule_tool import register_schedule_tools

        register_schedule_tools(registry, data_dir)

    if wants_module(COMPANY_SCRIPT_TOOLS, allowed):
        from backend.tools.company_script_tool import register_company_script_tools

        register_company_script_tools(registry, config=config, data_dir=data_dir)

    return registry
