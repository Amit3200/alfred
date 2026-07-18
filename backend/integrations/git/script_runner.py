"""Run read-only debug scripts inside a session repo workspace."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from backend.integrations.git.guardrails import (
    assert_write_enabled,
    assert_write_path_allowed,
    validate_readonly_script_content,
)
from backend.integrations.git.mirror import WorkspaceMirrorManager
from backend.integrations.git.sandbox import PathSandboxError, resolve_repo_path
from backend.integrations.git.api import resolve_repo_slug
from backend.integrations.git.write_ops import write_repo_file


def write_debug_script(
    mirror: WorkspaceMirrorManager,
    session_key: str,
    repo: str,
    *,
    filename: str,
    content: str,
) -> dict[str, Any]:
    """Write a validated read-only Python debug script under scripts/alfred_debug/."""
    git = mirror.git
    assert_write_enabled(git)
    name = filename.strip().replace("\\", "/").lstrip("/")
    if "/" in name:
        rel = name
    else:
        prefix = (git.debug_script_prefix or "scripts/alfred_debug/").rstrip("/")
        rel = f"{prefix}/{name}"
    if not rel.endswith(".py"):
        rel = f"{rel}.py"
    assert_write_path_allowed(git, rel, debug_script=True)
    validate_readonly_script_content(content)
    return write_repo_file(
        mirror,
        session_key,
        repo,
        path=rel,
        content=content,
        create_only=False,
        debug_script=True,
    )


def run_debug_script(
    mirror: WorkspaceMirrorManager,
    session_key: str,
    repo: str,
    *,
    script_path: str,
    args: list[str] | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Execute a read-only debug script with stdout/stderr capture."""
    git = mirror.git
    assert_write_enabled(git)
    slug = resolve_repo_slug(repo, git)
    rel = assert_write_path_allowed(git, script_path, debug_script=True)
    state = mirror.ensure_repo(session_key, slug)
    try:
        script_file = resolve_repo_path(state.path, rel)
    except PathSandboxError as exc:
        raise ValueError(str(exc)) from exc
    if not script_file.is_file():
        raise ValueError(f"Script not found: {rel}")

    content = script_file.read_text(encoding="utf-8", errors="replace")
    validate_readonly_script_content(content)

    cmd = ["python3", str(script_file)]
    for arg in args or []:
        arg = str(arg).strip()
        if not arg or ";" in arg or "|" in arg or "&" in arg:
            raise ValueError("Invalid script argument.")
        cmd.append(arg)

    timeout = timeout_seconds or git.script_timeout_seconds
    try:
        result = subprocess.run(
            cmd,
            cwd=str(state.path),
            capture_output=True,
            text=True,
            timeout=max(5, min(timeout, 600)),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"Script timed out after {timeout}s.") from exc

    return {
        "repo": slug,
        "script": rel,
        "exit_code": result.returncode,
        "stdout": (result.stdout or "")[:8000],
        "stderr": (result.stderr or "")[:4000],
    }
