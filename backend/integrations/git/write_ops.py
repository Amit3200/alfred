"""Session-scoped git write operations for Phase 1 PR flow."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from backend.integrations.git.api import resolve_repo_slug
from backend.integrations.git.guardrails import (
    assert_write_enabled,
    assert_write_path_allowed,
    protected_branches,
    validate_branch_name,
)
from backend.integrations.git.mirror import WorkspaceMirrorManager, _head_sha, _run_git
from backend.integrations.git.sandbox import PathSandboxError, resolve_repo_path
from backend.models.config import GitConfig

logger = logging.getLogger(__name__)


def _detect_default_base_branch(repo_dir: Path, git: GitConfig) -> str:
    configured = (git.default_base_branch or "").strip()
    if configured:
        return configured
    for candidate in ("main", "master", "develop"):
        try:
            _run_git(["git", "-C", str(repo_dir), "rev-parse", "--verify", f"origin/{candidate}"])
            return candidate
        except RuntimeError:
            continue
    try:
        ref = _run_git(["git", "-C", str(repo_dir), "symbolic-ref", "refs/remotes/origin/HEAD"])
        return ref.replace("refs/remotes/origin/", "").strip()
    except RuntimeError:
        return "main"


def prepare_write_branch(
    mirror: WorkspaceMirrorManager,
    session_key: str,
    repo: str,
    *,
    branch_name: str,
    base_branch: str | None = None,
) -> dict[str, Any]:
    """Fetch latest base branch and create an isolated feature branch in the session workspace."""
    git = mirror.git
    assert_write_enabled(git)
    slug = resolve_repo_slug(repo, git)
    branch = validate_branch_name(git, branch_name)
    state = mirror.ensure_repo(session_key, slug)
    repo_dir = state.path
    if not (repo_dir / ".git").exists():
        raise RuntimeError(f"Repository mirror missing at {repo_dir}")

    base = (base_branch or _detect_default_base_branch(repo_dir, git)).strip()
    if base.lower() in protected_branches(git):
        pass  # base is allowed to be protected
    else:
        validate_branch_name(git, base)

    depth = str(max(50, git.mirror_shallow_depth))
    _run_git(["git", "-C", str(repo_dir), "fetch", "origin", base, "--depth", depth])
    _run_git(["git", "-C", str(repo_dir), "checkout", "-B", base, f"origin/{base}"])
    _run_git(["git", "-C", str(repo_dir), "pull", "--ff-only", "origin", base])
    _run_git(["git", "-C", str(repo_dir), "checkout", "-b", branch])

    head = _head_sha(repo_dir)
    mirror._update_repo_ref(session_key, slug, ref=branch, head_sha=head)
    return {
        "repo": slug,
        "base_branch": base,
        "branch": branch,
        "head_sha": head,
        "path": str(repo_dir),
    }


def write_repo_file(
    mirror: WorkspaceMirrorManager,
    session_key: str,
    repo: str,
    *,
    path: str,
    content: str,
    create_only: bool = False,
    debug_script: bool = False,
) -> dict[str, Any]:
    git = mirror.git
    assert_write_enabled(git)
    slug = resolve_repo_slug(repo, git)
    rel = assert_write_path_allowed(git, path, debug_script=debug_script)
    state = mirror.ensure_repo(session_key, slug)
    try:
        file_path = resolve_repo_path(state.path, rel)
    except PathSandboxError as exc:
        raise ValueError(str(exc)) from exc

    if create_only and file_path.exists():
        raise ValueError(f"File already exists: {rel} (create_only=true).")
    if len(content) > git.write_max_file_bytes:
        raise ValueError(f"Content exceeds write_max_file_bytes ({git.write_max_file_bytes}).")

    existed = file_path.exists()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return {"repo": slug, "path": rel, "bytes": len(content.encode("utf-8")), "created": not existed}


def git_commit(
    mirror: WorkspaceMirrorManager,
    session_key: str,
    repo: str,
    *,
    message: str,
    paths: list[str] | None = None,
) -> dict[str, Any]:
    git = mirror.git
    assert_write_enabled(git)
    slug = resolve_repo_slug(repo, git)
    state = mirror.ensure_repo(session_key, slug)
    repo_dir = state.path
    msg = message.strip()
    if not msg:
        raise ValueError("commit message is required.")

    branch = _current_branch(repo_dir)
    if branch.lower() in protected_branches(git):
        raise ValueError(f"Cannot commit on protected branch {branch!r}.")

    if paths:
        for rel in paths:
            rel_norm = assert_write_path_allowed(git, rel, debug_script=False)
            _run_git(["git", "-C", str(repo_dir), "add", "--", rel_norm])
    else:
        _run_git(["git", "-C", str(repo_dir), "add", "-A"])

    status = _run_git(["git", "-C", str(repo_dir), "status", "--porcelain"])
    if not status.strip():
        raise ValueError("Nothing to commit — working tree clean.")

    _run_git(["git", "-C", str(repo_dir), "commit", "-m", msg])
    head = _head_sha(repo_dir)
    mirror._update_repo_ref(session_key, slug, ref=branch, head_sha=head)
    return {"repo": slug, "branch": branch, "head_sha": head, "message": msg}


def push_branch(
    mirror: WorkspaceMirrorManager,
    session_key: str,
    repo: str,
    *,
    branch: str | None = None,
) -> dict[str, Any]:
    git = mirror.git
    assert_write_enabled(git)
    slug = resolve_repo_slug(repo, git)
    state = mirror.ensure_repo(session_key, slug)
    repo_dir = state.path
    target = validate_branch_name(git, branch or _current_branch(repo_dir))

    _run_git(["git", "-C", str(repo_dir), "push", "-u", "origin", target])
    return {"repo": slug, "branch": target, "pushed": True}


def _current_branch(repo_dir: Path) -> str:
    try:
        return _run_git(["git", "-C", str(repo_dir), "rev-parse", "--abbrev-ref", "HEAD"]).strip()
    except RuntimeError:
        return "HEAD"
