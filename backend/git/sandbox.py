"""Resolve and sandbox paths inside a workspace repo mirror."""

from __future__ import annotations

from pathlib import Path


class PathSandboxError(ValueError):
    pass


def resolve_repo_path(repo_root: Path, relative_path: str) -> Path:
    """Return an absolute path inside repo_root; reject escapes."""
    rel = relative_path.strip().replace("\\", "/").lstrip("/")
    if not rel:
        raise PathSandboxError("Path cannot be empty.")
    if ".." in rel.split("/"):
        raise PathSandboxError("Path must stay inside the repository.")

    candidate = (repo_root / rel).resolve()
    root = repo_root.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PathSandboxError("Path must stay inside the repository.") from exc
    return candidate
