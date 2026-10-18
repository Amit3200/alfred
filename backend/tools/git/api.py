"""Git API tools — list PRs, get PR details, list repos (no local clone)."""

from __future__ import annotations

from typing import Any

from backend.ai.base import ToolSchema
from backend.integrations.git.api import GitApiClient, resolve_repo_slug
from backend.models.config import AlfredConfig
from backend.tools.base.function_tool import FunctionTool
from backend.tools.base.tool import BaseTool, ToolContext
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


def _client(ctx: ToolContext) -> GitApiClient:
    return GitApiClient.from_alfred_config(ctx.config)


def list_my_prs(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    state = str(args.get("state") or "open")
    prs = _client(ctx).list_my_prs(state=state)
    return ToolResult.pr_list(prs, state=state)


def list_prs(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    repo = str(args.get("repo") or "").strip()
    if not repo:
        return ToolResult.error("repo is required (owner/name).")
    try:
        repo = resolve_repo_slug(repo, ctx.config.git)
    except ValueError as exc:
        return ToolResult.error(str(exc))
    state = str(args.get("state") or "open")
    prs = _client(ctx).list_prs(repo, state=state)
    return ToolResult.pr_list(prs, state=state)


def get_pr(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    repo = str(args.get("repo") or "").strip()
    number = args.get("number")
    if not repo or number is None:
        return ToolResult.error("repo and number are required.")
    try:
        repo = resolve_repo_slug(repo, ctx.config.git)
    except ValueError as exc:
        return ToolResult.error(str(exc))
    data = _client(ctx).get_pr(repo, int(number))
    return ToolResult.pr_detail(data)


def get_pr_changes(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    repo = str(args.get("repo") or "").strip()
    number = args.get("number")
    if not repo or number is None:
        return ToolResult.error("repo and number are required.")
    try:
        repo = resolve_repo_slug(repo, ctx.config.git)
    except ValueError as exc:
        return ToolResult.error(str(exc))
    client = _client(ctx)
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


def list_repos(ctx: ToolContext, _args: dict[str, Any]) -> ToolResult:
    repos = _client(ctx).list_repos()
    return ToolResult.repo_list(repos)


def git_api_tools() -> list[BaseTool]:
    return [
        FunctionTool(
            name="list_my_prs",
            capability="git.pr.read",
            operation="list_mine",
            domain="git",
            schema=LIST_MY_PRS,
            run_fn=list_my_prs,
            produces=("prs",),
            next_tools=("get_pr",),
        ),
        FunctionTool(
            name="list_prs",
            capability="git.pr.read",
            operation="list",
            domain="git",
            schema=LIST_PRS,
            run_fn=list_prs,
            produces=("prs",),
            next_tools=("get_pr",),
        ),
        FunctionTool(
            name="get_pr",
            capability="git.pr.read",
            operation="read",
            domain="git",
            schema=GET_PR,
            run_fn=get_pr,
            consumes=("prs",),
            produces=("pr",),
            next_tools=("get_pr_changes",),
        ),
        FunctionTool(
            name="get_pr_changes",
            capability="git.pr.read",
            operation="diff",
            domain="git",
            schema=GET_PR_CHANGES,
            run_fn=get_pr_changes,
            consumes=("pr",),
            produces=("pr_files",),
        ),
        FunctionTool(
            name="list_repos",
            capability="git.pr.read",
            operation="list_repos",
            domain="git",
            schema=LIST_REPOS,
            run_fn=list_repos,
            produces=("repos",),
        ),
    ]


def register_git_api_tools(registry: ToolRegistry, config: AlfredConfig) -> None:
    registry.alfred_config = config
    from backend.tools.git.bundle import GitApiToolBundle

    GitApiToolBundle().register(registry)
