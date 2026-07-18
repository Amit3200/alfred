"""Phase 1 git write tools — isolated workspace branches, PR creation, debug scripts."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.ai.base import ToolSchema
from backend.integrations.git.api import GitApiClient, resolve_repo_slug
from backend.integrations.git.mirror import WorkspaceMirrorManager
from backend.integrations.git.script_runner import run_debug_script, write_debug_script
from backend.integrations.git.write_ops import (
    git_commit,
    prepare_write_branch,
    push_branch,
    write_repo_file,
)
from backend.models.config import AlfredConfig
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult

logger = logging.getLogger(__name__)

GIT_PREPARE_BRANCH = ToolSchema(
    name="git_prepare_branch",
    description=(
        "Fetch latest base branch (default main) and create a new feature branch in this "
        "conversation's isolated workspace. Call this before any file writes."
    ),
    parameters={
        "type": "object",
        "properties": {
            "repo": {"type": "string", "description": "Repository slug owner/name."},
            "branch_name": {
                "type": "string",
                "description": "New branch name, e.g. alfred/add-logging-instrumentation.",
            },
            "base_branch": {
                "type": "string",
                "description": "Base branch to pull (default: git.default_base_branch or main).",
            },
        },
        "required": ["repo", "branch_name"],
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
        "Script must only read data (no writes, network, or subprocess)."
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


def register_git_write_tools(
    registry: ToolRegistry,
    *,
    config: AlfredConfig,
    data_dir: Path,
) -> None:
    if not config.git.enabled or not config.git.write_enabled:
        return

    mirror = WorkspaceMirrorManager(config.git, data_dir)
    client = GitApiClient(config.git)

    def _session_key() -> str:
        key = getattr(registry, "workspace_id", None)
        if not key:
            raise RuntimeError("No workspace session — write tools require a conversation context.")
        return str(key)

    def _handle_value_error(exc: ValueError) -> ToolResult:
        return ToolResult.error(str(exc))

    def prepare_branch_handler(args: dict[str, Any]) -> ToolResult:
        try:
            data = prepare_write_branch(
                mirror,
                _session_key(),
                str(args.get("repo") or ""),
                branch_name=str(args.get("branch_name") or ""),
                base_branch=str(args.get("base_branch") or "") or None,
            )
            return ToolResult(kind="git_branch", data=data)
        except (ValueError, RuntimeError) as exc:
            return _handle_value_error(exc) if isinstance(exc, ValueError) else ToolResult.error(str(exc))

    def write_file_handler(args: dict[str, Any]) -> ToolResult:
        try:
            data = write_repo_file(
                mirror,
                _session_key(),
                str(args.get("repo") or ""),
                path=str(args.get("path") or ""),
                content=str(args.get("content") or ""),
                create_only=bool(args.get("create_only")),
            )
            return ToolResult(kind="git_write", data=data)
        except (ValueError, RuntimeError) as exc:
            return ToolResult.error(str(exc))

    def write_debug_script_handler(args: dict[str, Any]) -> ToolResult:
        try:
            data = write_debug_script(
                mirror,
                _session_key(),
                str(args.get("repo") or ""),
                filename=str(args.get("filename") or ""),
                content=str(args.get("content") or ""),
            )
            return ToolResult(kind="git_write", data={**data, "kind": "debug_script"})
        except (ValueError, RuntimeError) as exc:
            return ToolResult.error(str(exc))

    def run_debug_script_handler(args: dict[str, Any]) -> ToolResult:
        try:
            raw_args = args.get("args")
            script_args = [str(a) for a in raw_args] if isinstance(raw_args, list) else None
            data = run_debug_script(
                mirror,
                _session_key(),
                str(args.get("repo") or ""),
                script_path=str(args.get("script_path") or ""),
                args=script_args,
            )
            return ToolResult(kind="script_run", data=data)
        except (ValueError, RuntimeError) as exc:
            return ToolResult.error(str(exc))

    def git_commit_handler(args: dict[str, Any]) -> ToolResult:
        try:
            paths_raw = args.get("paths")
            paths = [str(p) for p in paths_raw] if isinstance(paths_raw, list) else None
            data = git_commit(
                mirror,
                _session_key(),
                str(args.get("repo") or ""),
                message=str(args.get("message") or ""),
                paths=paths,
            )
            return ToolResult(kind="git_commit", data=data)
        except (ValueError, RuntimeError) as exc:
            return ToolResult.error(str(exc))

    def push_branch_handler(args: dict[str, Any]) -> ToolResult:
        try:
            branch = str(args.get("branch") or "").strip() or None
            data = push_branch(
                mirror,
                _session_key(),
                str(args.get("repo") or ""),
                branch=branch,
            )
            return ToolResult(kind="git_push", data=data)
        except (ValueError, RuntimeError) as exc:
            return ToolResult.error(str(exc))

    def create_pr_handler(args: dict[str, Any]) -> ToolResult:
        repo = str(args.get("repo") or "").strip()
        title = str(args.get("title") or "").strip()
        head = str(args.get("head") or "").strip()
        if not repo or not title or not head:
            return ToolResult.error("repo, title, and head are required.")
        try:
            slug = resolve_repo_slug(repo, config.git)
            base = str(args.get("base") or config.git.default_base_branch or "main").strip()
            detail = client.create_pull_request(
                slug,
                title=title,
                head=head,
                base=base,
                body=str(args.get("body") or ""),
                draft=bool(args.get("draft", True)),
            )
            return ToolResult(kind="pr_created", data={"pr": detail})
        except (ValueError, RuntimeError) as exc:
            return ToolResult.error(str(exc))

    registry.register(GIT_PREPARE_BRANCH, prepare_branch_handler)
    registry.register(WRITE_FILE, write_file_handler)
    registry.register(WRITE_DEBUG_SCRIPT, write_debug_script_handler)
    registry.register(RUN_DEBUG_SCRIPT, run_debug_script_handler)
    registry.register(GIT_COMMIT, git_commit_handler)
    registry.register(GIT_PUSH_BRANCH, push_branch_handler)
    registry.register(CREATE_PULL_REQUEST, create_pr_handler)
