"""Phase 1 git write tools — isolated workspace branches, PR creation, debug scripts."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.ai.base import ToolSchema
from backend.integrations.git.api import GitApiClient, resolve_repo_slug
from backend.integrations.git.guardrails import resolve_alfred_pr_branch_name
from backend.integrations.git.mirror import WorkspaceMirrorManager
from backend.integrations.git.script_runner import run_debug_script, write_debug_script
from backend.integrations.git.write_ops import (
    git_commit,
    prepare_write_branch,
    push_branch,
    write_repo_file,
)
from backend.models.config import AlfredConfig
from backend.tools.base.function_tool import FunctionTool
from backend.tools.base.tool import BaseTool, ToolContext
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult

logger = logging.getLogger(__name__)

ALFRED_PR_LABEL_GENERATED = "alfred-generated"
ALFRED_PR_LABEL_PLAN = "alfred-plan"

GIT_PREPARE_BRANCH = ToolSchema(
    name="git_prepare_branch",
    description=(
        "Fetch latest base branch (auto-detects origin default, e.g. dev or main) and create a "
        "conversation's isolated workspace. Call this before any file writes."
    ),
    parameters={
        "type": "object",
        "properties": {
            "repo": {"type": "string", "description": "Repository slug owner/name."},
            "branch_context": {
                "type": "string",
                "description": (
                    "Short slug for the change, e.g. instrument-checkout-handler. "
                    "Branch becomes alfred/pr/<slug>."
                ),
            },
            "branch_name": {
                "type": "string",
                "description": (
                    "Optional explicit branch name (alfred/pr/<slug>). "
                    "When omitted, derived from branch_context."
                ),
            },
            "base_branch": {
                "type": "string",
                "description": (
                    "Base branch to pull. Omit to use git.default_base_branch or the remote "
                    "default (origin/HEAD)."
                ),
            },
        },
        "required": ["repo"],
    },
)

WRITE_FILE = ToolSchema(
    name="write_file",
    description=(
        "Write or overwrite a text file in the session workspace. Phase 1 blocks infra, "
        "lockfiles, and secrets paths. Prefer small, additive changes with tests."
    ),
    parameters={
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "path": {"type": "string", "description": "Repo-relative file path."},
            "content": {"type": "string", "description": "Full file contents (UTF-8)."},
            "create_only": {
                "type": "boolean",
                "description": "If true, fail when the file already exists.",
            },
        },
        "required": ["repo", "path", "content"],
    },
)

WRITE_DEBUG_SCRIPT = ToolSchema(
    name="write_debug_script",
    description=(
        "Write a read-only Python debug script under scripts/alfred_debug/. "
        "Script must only read data (no file writes, network, shell=True, or os.system)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "filename": {
                "type": "string",
                "description": "Script name or path under scripts/alfred_debug/, e.g. inspect_orders.py.",
            },
            "content": {"type": "string", "description": "Python source code."},
        },
        "required": ["repo", "filename", "content"],
    },
)

RUN_DEBUG_SCRIPT = ToolSchema(
    name="run_debug_script",
    description="Run a read-only debug script from scripts/alfred_debug/ and return stdout/stderr.",
    parameters={
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "script_path": {
                "type": "string",
                "description": "Repo-relative path to the script under scripts/alfred_debug/.",
            },
            "args": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional CLI args passed to the script.",
            },
        },
        "required": ["repo", "script_path"],
    },
)

GIT_COMMIT = ToolSchema(
    name="git_commit",
    description="Stage and commit changes on the current feature branch (never on main/master).",
    parameters={
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "message": {"type": "string", "description": "Conventional commit message."},
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of paths to stage; default stages all changes.",
            },
        },
        "required": ["repo", "message"],
    },
)

GIT_PUSH_BRANCH = ToolSchema(
    name="git_push_branch",
    description="Push the current or named feature branch to origin (never protected branches).",
    parameters={
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "branch": {
                "type": "string",
                "description": "Branch to push; default is current branch.",
            },
        },
        "required": ["repo"],
    },
)

CREATE_PULL_REQUEST = ToolSchema(
    name="create_pull_request",
    description="Open a pull/merge request on GitHub or GitLab after pushing the feature branch.",
    parameters={
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "title": {"type": "string"},
            "body": {"type": "string", "description": "PR description with plan, tests, and checklist."},
            "head": {"type": "string", "description": "Head branch (feature branch)."},
            "base": {
                "type": "string",
                "description": "Base branch (default main).",
            },
            "draft": {
                "type": "boolean",
                "description": "Open as draft PR when true (recommended for Phase 1).",
            },
        },
        "required": ["repo", "title", "head"],
    },
)


def alfred_pr_labels_for_registry(registry: ToolRegistry, data_dir: Path) -> list[str]:
    """Labels applied to Alfred-created PRs for filtering and automation."""
    labels = [ALFRED_PR_LABEL_GENERATED]
    gov = getattr(registry, "governance", None)
    if gov is None:
        return labels

    from backend.orchestrator.planning import plan_exists_for_task, session_plan_path

    if plan_exists_for_task(gov.task.id, data_dir):
        labels.append(ALFRED_PR_LABEL_PLAN)
    elif session_plan_path(gov.session):
        labels.append(ALFRED_PR_LABEL_PLAN)
    return labels


def _workspace_id(ctx: ToolContext) -> str:
    registry = ctx.get("registry")
    key = getattr(registry, "workspace_id", None) or ctx.session_key
    if not key:
        raise RuntimeError("No workspace session — write tools require a conversation context.")
    return str(key)


def _mirror(ctx: ToolContext) -> WorkspaceMirrorManager:
    if ctx.data_dir is None:
        raise RuntimeError("data_dir is required for git write tools.")
    return WorkspaceMirrorManager(ctx.config.git, ctx.data_dir)


def git_prepare_branch(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    try:
        branch_name = str(args.get("branch_name") or "").strip() or None
        branch_context = str(args.get("branch_context") or "").strip() or None
        if not branch_name and not branch_context:
            return ToolResult.error("branch_context or branch_name is required.")
        resolved_branch = resolve_alfred_pr_branch_name(
            branch_name=branch_name,
            branch_context=branch_context,
        )
        data = prepare_write_branch(
            _mirror(ctx),
            _workspace_id(ctx),
            str(args.get("repo") or ""),
            branch_name=resolved_branch,
            base_branch=str(args.get("base_branch") or "") or None,
        )
        return ToolResult(kind="git_branch", data={**data, "branch_name": resolved_branch})
    except (ValueError, RuntimeError) as exc:
        return ToolResult.error(str(exc))


def write_file(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    try:
        data = write_repo_file(
            _mirror(ctx),
            _workspace_id(ctx),
            str(args.get("repo") or ""),
            path=str(args.get("path") or ""),
            content=str(args.get("content") or ""),
            create_only=bool(args.get("create_only")),
        )
        return ToolResult(kind="git_write", data=data)
    except (ValueError, RuntimeError) as exc:
        return ToolResult.error(str(exc))


def write_debug_script_tool(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    try:
        data = write_debug_script(
            _mirror(ctx),
            _workspace_id(ctx),
            str(args.get("repo") or ""),
            filename=str(args.get("filename") or ""),
            content=str(args.get("content") or ""),
        )
        return ToolResult(kind="git_write", data={**data, "kind": "debug_script"})
    except (ValueError, RuntimeError) as exc:
        return ToolResult.error(str(exc))


def run_debug_script_tool(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    try:
        raw_args = args.get("args")
        script_args = [str(a) for a in raw_args] if isinstance(raw_args, list) else None
        data = run_debug_script(
            _mirror(ctx),
            _workspace_id(ctx),
            str(args.get("repo") or ""),
            script_path=str(args.get("script_path") or ""),
            args=script_args,
        )
        return ToolResult(kind="script_run", data=data)
    except (ValueError, RuntimeError) as exc:
        return ToolResult.error(str(exc))


def git_commit_tool(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    try:
        paths_raw = args.get("paths")
        paths = [str(p) for p in paths_raw] if isinstance(paths_raw, list) else None
        data = git_commit(
            _mirror(ctx),
            _workspace_id(ctx),
            str(args.get("repo") or ""),
            message=str(args.get("message") or ""),
            paths=paths,
        )
        return ToolResult(kind="git_commit", data=data)
    except (ValueError, RuntimeError) as exc:
        return ToolResult.error(str(exc))


def git_push_branch(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    try:
        branch = str(args.get("branch") or "").strip() or None
        data = push_branch(
            _mirror(ctx),
            _workspace_id(ctx),
            str(args.get("repo") or ""),
            branch=branch,
        )
        return ToolResult(kind="git_push", data=data)
    except (ValueError, RuntimeError) as exc:
        return ToolResult.error(str(exc))


def create_pull_request(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    repo = str(args.get("repo") or "").strip()
    title = str(args.get("title") or "").strip()
    head = str(args.get("head") or "").strip()
    if not repo or not title or not head:
        return ToolResult.error("repo, title, and head are required.")
    if ctx.data_dir is None:
        return ToolResult.error("data_dir is required for git write tools.")
    try:
        slug = resolve_repo_slug(repo, ctx.config.git)
        from backend.integrations.git.write_ops import _resolve_base_branch

        mirror = _mirror(ctx)
        state = mirror.ensure_repo(_workspace_id(ctx), slug)
        base_arg = str(args.get("base") or ctx.config.git.default_base_branch or "").strip() or None
        base = _resolve_base_branch(state.path, ctx.config.git, base_arg)
        normalized_head = resolve_alfred_pr_branch_name(branch_name=head)
        registry = ctx.get("registry")
        labels = alfred_pr_labels_for_registry(registry, ctx.data_dir) if registry is not None else [ALFRED_PR_LABEL_GENERATED]
        client = GitApiClient(ctx.config.git)
        detail = client.create_pull_request(
            slug,
            title=title,
            head=normalized_head,
            base=base,
            body=str(args.get("body") or ""),
            draft=bool(args.get("draft", True)),
            labels=labels,
        )
        return ToolResult(kind="pr_created", data={"pr": detail, "labels": labels})
    except (ValueError, RuntimeError) as exc:
        return ToolResult.error(str(exc))


def git_write_tools() -> list[BaseTool]:
    return [
        FunctionTool(
            name="git_prepare_branch",
            capability="git.write.pr",
            operation="prepare_branch",
            domain="git",
            schema=GIT_PREPARE_BRANCH,
            run_fn=git_prepare_branch,
            produces=("branch_name",),
            next_tools=("write_file",),
        ),
        FunctionTool(
            name="write_file",
            capability="git.write.pr",
            operation="write",
            domain="git",
            schema=WRITE_FILE,
            run_fn=write_file,
            consumes=("branch_name",),
            produces=("path",),
            next_tools=("git_commit",),
        ),
        FunctionTool(
            name="write_debug_script",
            capability="git.write.pr",
            operation="write_debug",
            domain="git",
            schema=WRITE_DEBUG_SCRIPT,
            run_fn=write_debug_script_tool,
            next_tools=("run_debug_script",),
        ),
        FunctionTool(
            name="run_debug_script",
            capability="git.write.pr",
            operation="run_debug",
            domain="git",
            schema=RUN_DEBUG_SCRIPT,
            run_fn=run_debug_script_tool,
        ),
        FunctionTool(
            name="git_commit",
            capability="git.write.pr",
            operation="commit",
            domain="git",
            schema=GIT_COMMIT,
            run_fn=git_commit_tool,
            consumes=("path",),
            produces=("commit",),
            next_tools=("git_push_branch",),
        ),
        FunctionTool(
            name="git_push_branch",
            capability="git.write.pr",
            operation="push",
            domain="git",
            schema=GIT_PUSH_BRANCH,
            run_fn=git_push_branch,
            consumes=("commit",),
            produces=("branch",),
            next_tools=("create_pull_request",),
        ),
        FunctionTool(
            name="create_pull_request",
            capability="git.write.pr",
            operation="create_pr",
            domain="git",
            schema=CREATE_PULL_REQUEST,
            run_fn=create_pull_request,
            consumes=("branch",),
            produces=("pr",),
        ),
    ]


def register_git_write_tools(
    registry: ToolRegistry,
    *,
    config: AlfredConfig,
    data_dir: Path,
) -> None:
    if not config.git.enabled or not config.git.write_enabled:
        return
    registry.alfred_config = config
    registry.data_dir = data_dir
    from backend.tools.git.bundle import GitWriteToolBundle

    GitWriteToolBundle().register(registry)
