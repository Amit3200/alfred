"""Local git mirror tools — grep, read, log, blame (session-scoped workspaces)."""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from backend.ai.base import ToolSchema
from backend.integrations.git.api import resolve_repo_slug
from backend.integrations.git.mirror import WorkspaceMirrorManager
from backend.integrations.git.sandbox import PathSandboxError, resolve_repo_path
from backend.models.config import AlfredConfig
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult

logger = logging.getLogger(__name__)

_REF_PROPERTY = {
    "ref": {
        "type": "string",
        "description": "Branch, tag, or commit SHA to checkout (e.g. feature/sqs or main).",
    },
}

GREP_REPO = ToolSchema(
    name="grep_repo",
    description="Search for a regex pattern in a repository mirror.",
    parameters={
        "type": "object",
        "properties": {
            "repo": {"type": "string", "description": "Repository slug owner/name."},
            "pattern": {"type": "string", "description": "Regex or plain text to search."},
            "path": {
                "type": "string",
                "description": "Optional subdirectory within the repo.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum matches to return (default 20).",
            },
            **_REF_PROPERTY,
        },
        "required": ["repo", "pattern"],
    },
)

READ_FILE = ToolSchema(
    name="read_file",
    description="Read a text file from a repository mirror with optional line range.",
    parameters={
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "path": {"type": "string", "description": "File path relative to repo root."},
            "start_line": {"type": "integer", "description": "1-based start line (default 1)."},
            "end_line": {"type": "integer", "description": "1-based inclusive end line."},
            **_REF_PROPERTY,
        },
        "required": ["repo", "path"],
    },
)

GIT_LOG = ToolSchema(
    name="git_log",
    description="Show recent commits for a path or entire repo.",
    parameters={
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "path": {"type": "string", "description": "Optional file/dir path."},
            "limit": {"type": "integer", "description": "Max commits (default 10)."},
            **_REF_PROPERTY,
        },
        "required": ["repo"],
    },
)

GIT_BLAME = ToolSchema(
    name="git_blame",
    description="Show blame for a file line range.",
    parameters={
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "path": {"type": "string"},
            "start_line": {"type": "integer"},
            "end_line": {"type": "integer"},
            **_REF_PROPERTY,
        },
        "required": ["repo", "path"],
    },
)

GIT_SHOW = ToolSchema(
    name="git_show",
    description="Show commit details and diff stat for a ref (SHA, tag, or branch).",
    parameters={
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "ref": {
                "type": "string",
                "description": "Commit SHA, tag, or branch name.",
            },
        },
        "required": ["repo", "ref"],
    },
)


def register_local_git_tools(
    registry: ToolRegistry,
    *,
    config: AlfredConfig,
    data_dir: Path,
) -> None:
    mirror = WorkspaceMirrorManager(config.git, data_dir)

    def _session_key() -> str:
        key = getattr(registry, "workspace_id", None)
        if not key:
            raise RuntimeError("No workspace session — mirror tools require a conversation context.")
        return str(key)

    def _optional_ref(args: dict[str, Any]) -> str | None:
        ref = str(args.get("ref") or "").strip()
        return ref or None

    def grep_repo_handler(args: dict[str, Any]) -> ToolResult:
        repo = str(args.get("repo") or "").strip()
        pattern = str(args.get("pattern") or "").strip()
        if not repo or not pattern:
            return ToolResult.error("repo and pattern are required.")
        subpath = str(args.get("path") or "").strip()
        max_results = int(args.get("max_results") or 20)
        ref = _optional_ref(args)
        slug = resolve_repo_slug(repo, config.git)
        state = mirror.ensure_repo(_session_key(), slug, ref=ref)
        search_root = state.path
        if subpath:
            search_root = resolve_repo_path(state.path, subpath)
        matches = _grep_paths(search_root, pattern, max_results=max_results)
        return ToolResult(
            kind="code_grep",
            data={
                "repo": slug,
                "pattern": pattern,
                "path": subpath or None,
                "matches": matches,
                "refreshed": state.refreshed,
                "head_sha": state.head_sha,
                "ref": ref,
            },
        )

    def read_file_handler(args: dict[str, Any]) -> ToolResult:
        repo = str(args.get("repo") or "").strip()
        rel = str(args.get("path") or "").strip()
        if not repo or not rel:
            return ToolResult.error("repo and path are required.")
        start = max(1, int(args.get("start_line") or 1))
        end = args.get("end_line")
        end_line = int(end) if end is not None else start + 120
        ref = _optional_ref(args)
        slug = resolve_repo_slug(repo, config.git)
        state = mirror.ensure_repo(_session_key(), slug, ref=ref)
        try:
            file_path = resolve_repo_path(state.path, rel)
        except PathSandboxError as exc:
            return ToolResult.error(str(exc))
        if not file_path.is_file():
            return ToolResult.error(f"File not found: {rel}")
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        end_line = min(end_line, len(lines))
        if start > len(lines):
            return ToolResult.error(f"Start line {start} beyond file length ({len(lines)}).")
        snippet = lines[start - 1 : end_line]
        return ToolResult(
            kind="file_content",
            data={
                "repo": slug,
                "path": rel,
                "start_line": start,
                "end_line": end_line,
                "content": "\n".join(snippet),
                "total_lines": len(lines),
                "ref": ref,
            },
        )

    def git_log_handler(args: dict[str, Any]) -> ToolResult:
        repo = str(args.get("repo") or "").strip()
        if not repo:
            return ToolResult.error("repo is required.")
        limit = max(1, min(int(args.get("limit") or 10), 50))
        rel = str(args.get("path") or "").strip()
        ref = _optional_ref(args)
        slug = resolve_repo_slug(repo, config.git)
        state = mirror.ensure_repo(_session_key(), slug, ref=ref)
        cmd = [
            "git",
            "-C",
            str(state.path),
            "log",
            f"-n{limit}",
            "--pretty=format:%h %an %s",
        ]
        if rel:
            cmd.append("--")
            cmd.append(rel)
        output = _run(cmd)
        commits = [line for line in output.splitlines() if line.strip()]
        return ToolResult(
            kind="git_log",
            data={"repo": slug, "path": rel or None, "commits": commits, "ref": ref},
        )

    def git_blame_handler(args: dict[str, Any]) -> ToolResult:
        repo = str(args.get("repo") or "").strip()
        rel = str(args.get("path") or "").strip()
        if not repo or not rel:
            return ToolResult.error("repo and path are required.")
        start = max(1, int(args.get("start_line") or 1))
        end = max(start, int(args.get("end_line") or start + 20))
        ref = _optional_ref(args)
        slug = resolve_repo_slug(repo, config.git)
        state = mirror.ensure_repo(_session_key(), slug, ref=ref)
        try:
            resolve_repo_path(state.path, rel)
        except PathSandboxError as exc:
            return ToolResult.error(str(exc))
        output = _run(
            [
                "git",
                "-C",
                str(state.path),
                "blame",
                "-L",
                f"{start},{end}",
                "--",
                rel,
            ]
        )
        return ToolResult(
            kind="git_blame",
            data={
                "repo": slug,
                "path": rel,
                "start_line": start,
                "end_line": end,
                "lines": output.splitlines(),
                "ref": ref,
            },
        )

    def git_show_handler(args: dict[str, Any]) -> ToolResult:
        repo = str(args.get("repo") or "").strip()
        ref = str(args.get("ref") or "").strip()
        if not repo or not ref:
            return ToolResult.error("repo and ref are required.")
        slug = resolve_repo_slug(repo, config.git)
        state = mirror.ensure_repo(_session_key(), slug, ref=ref)
        output = _run(
            [
                "git",
                "-C",
                str(state.path),
                "show",
                "--stat",
                "--format=medium",
                "HEAD",
            ]
        )
        return ToolResult(
            kind="git_show",
            data={"repo": slug, "ref": ref, "output": output[:8000]},
        )

    registry.register(GREP_REPO, grep_repo_handler)
    registry.register(READ_FILE, read_file_handler)
    registry.register(GIT_LOG, git_log_handler)
    registry.register(GIT_BLAME, git_blame_handler)
    registry.register(GIT_SHOW, git_show_handler)


def _grep_paths(root: Path, pattern: str, *, max_results: int) -> list[dict[str, Any]]:
    if root.is_file():
        return _grep_file(root, root.parent, pattern, max_results=max_results)
    matches: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".woff", ".woff2"}:
            continue
        remaining = max_results - len(matches)
        if remaining <= 0:
            break
        matches.extend(_grep_file(path, root, pattern, max_results=remaining))
    return matches[:max_results]


def _grep_file(
    file_path: Path,
    repo_root: Path,
    pattern: str,
    *,
    max_results: int,
) -> list[dict[str, Any]]:
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    rel = str(file_path.relative_to(repo_root)).replace("\\", "/")
    regex = re.compile(pattern, re.IGNORECASE)
    out: list[dict[str, Any]] = []
    for index, line in enumerate(text.splitlines(), start=1):
        if regex.search(line):
            out.append({"path": rel, "line": index, "text": line.strip()[:240]})
            if len(out) >= max_results:
                break
    return out


def _run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "git command failed").strip()
        raise RuntimeError(detail[:500])
    return result.stdout or ""
