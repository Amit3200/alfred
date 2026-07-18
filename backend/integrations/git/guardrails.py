"""Phase 1 git write guardrails — branch, path, and script content checks."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from backend.models.config import GitConfig

DEFAULT_PROTECTED_BRANCHES = ("main", "master", "production", "prod")

DEFAULT_WRITE_BLOCKED_PREFIXES = (
    ".github/",
    ".gitlab/",
    "infra/",
    "terraform/",
    "Dockerfile",
    "docker-compose",
    ".env",
    "secrets",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "poetry.lock",
    "requirements.txt",
    "go.mod",
    "go.sum",
)

DEFAULT_DEBUG_SCRIPT_PREFIX = "scripts/alfred_debug/"

# Patterns that must not appear in read-only debug scripts.
_FORBIDDEN_SCRIPT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"open\s*\([^)]*,\s*['\"]w", re.I), "file open in write mode"),
    (re.compile(r"open\s*\([^)]*,\s*['\"]a", re.I), "file open in append mode"),
    (re.compile(r"\bos\.remove\b|\bos\.unlink\b|\bos\.rmdir\b", re.I), "os file deletion"),
    (re.compile(r"\bshutil\.rmtree\b|\bshutil\.move\b", re.I), "shutil destructive ops"),
    (re.compile(r"\bsubprocess\b", re.I), "subprocess (use stdlib read-only logic only)"),
    (re.compile(r"\bsocket\b|\brequests\b|\bhttpx\b|\burllib\b", re.I), "network I/O"),
    (re.compile(r"\bgit\s+", re.I), "shell git commands inside script"),
    (re.compile(r"\brm\s+-|\brmdir\b", re.I), "shell deletion"),
)

_BRANCH_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9._/-]*[a-zA-Z0-9])?$")


def protected_branches(git: GitConfig) -> set[str]:
    branches = {b.lower() for b in DEFAULT_PROTECTED_BRANCHES}
    branches.update(b.lower() for b in git.protected_branches if b.strip())
    return branches


def assert_write_enabled(git: GitConfig) -> None:
    if not git.enabled:
        raise ValueError("Git integration is disabled.")
    if not git.write_enabled:
        raise ValueError(
            "Git write tools are disabled. Set git.write_enabled: true in config to enable Phase 1 PR flow."
        )
    if not git.token:
        raise ValueError("Git token is not configured.")


def validate_branch_name(git: GitConfig, branch: str) -> str:
    name = branch.strip()
    if not name:
        raise ValueError("branch_name is required.")
    if name.lower() in protected_branches(git):
        raise ValueError(f"Branch {name!r} is protected and cannot be used for writes.")
    if ".." in name or name.startswith("-") or name.endswith("/") or "//" in name:
        raise ValueError(f"Invalid branch name: {name!r}")
    if not _BRANCH_RE.match(name):
        raise ValueError(f"Invalid branch name: {name!r}")
    return name


def normalize_repo_path(relative_path: str) -> str:
    rel = relative_path.strip().replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise ValueError("Path must stay inside the repository.")
    return rel


def assert_write_path_allowed(git: GitConfig, relative_path: str, *, debug_script: bool = False) -> str:
    rel = normalize_repo_path(relative_path)
    blocked = list(git.write_blocked_prefixes or DEFAULT_WRITE_BLOCKED_PREFIXES)
    lower = rel.lower()
    for prefix in blocked:
        p = prefix.lower().rstrip("/")
        if lower == p or lower.startswith(p + "/"):
            raise ValueError(f"Writes to {rel!r} are blocked in Phase 1 (matches {prefix!r}).")

    if debug_script:
        debug_prefix = (git.debug_script_prefix or DEFAULT_DEBUG_SCRIPT_PREFIX).lower()
        if not lower.startswith(debug_prefix):
            raise ValueError(
                f"Debug scripts must live under {git.debug_script_prefix or DEFAULT_DEBUG_SCRIPT_PREFIX!r}."
            )
        if not lower.endswith(".py"):
            raise ValueError("Debug scripts must be Python (.py) files.")
    else:
        allowed_prefixes = [p for p in (git.write_allowed_prefixes or []) if p.strip()]
        if allowed_prefixes:
            if not any(lower.startswith(p.lower().rstrip("/") + "/") or lower == p.lower().rstrip("/") for p in allowed_prefixes):
                raise ValueError(
                    f"Path {rel!r} is outside write_allowed_prefixes: {allowed_prefixes}"
                )
    return rel


def validate_readonly_script_content(content: str) -> None:
    for pattern, label in _FORBIDDEN_SCRIPT_PATTERNS:
        if pattern.search(content):
            raise ValueError(f"Debug script rejected — {label} is not allowed in read-only scripts.")


ALFRED_PR_BRANCH_PREFIX = "alfred/pr"


def slugify_branch_context(text: str, *, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-zA-Z0-9-]+", "-", text.strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    if not slug:
        slug = "change"
    trimmed = slug[:max_len].rstrip("-")
    return trimmed or "change"


def format_alfred_pr_branch_name(branch_context: str) -> str:
    return f"{ALFRED_PR_BRANCH_PREFIX}/{slugify_branch_context(branch_context)}"


def resolve_alfred_pr_branch_name(
    *,
    branch_name: str | None = None,
    branch_context: str | None = None,
) -> str:
    """Normalize Alfred PR branches to ``alfred/pr/<slug>``."""
    name = (branch_name or "").strip()
    context = (branch_context or "").strip()

    if name.startswith(f"{ALFRED_PR_BRANCH_PREFIX}/"):
        return name

    if name.startswith("alfred/"):
        context = context or name[len("alfred/") :]
    elif name:
        context = context or name

    if not context:
        from datetime import datetime, timezone

        context = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")

    return format_alfred_pr_branch_name(context)


def suggest_branch_name(branch_context: str = "change") -> str:
    return format_alfred_pr_branch_name(branch_context)
