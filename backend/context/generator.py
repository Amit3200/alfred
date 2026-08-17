"""Generate and load markdown repo context from shared mirror checkouts."""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.integrations.git.api import resolve_repo_slug
from backend.models.config import AIConfig, GitConfig
from backend.paths import repo_context_dir, shared_repos_dir

logger = logging.getLogger(__name__)

MANIFEST_NAME = "manifest.json"
OVERVIEW_NAME = "overview.md"
LAYOUT_NAME = "layout.md"
MAX_PROMPT_CHARS = 8000
MAX_README_CHARS = 2500

_SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".github",
        "node_modules",
        "dist",
        "build",
        ".next",
        "coverage",
        "vendor",
        "__pycache__",
        ".venv",
        "venv",
        ".alfred",
        "graphify-out",
    }
)
_KEY_FILES = (
    "package.json",
    "pyproject.toml",
    "go.mod",
    "Cargo.toml",
    "pnpm-workspace.yaml",
    "turbo.json",
    "nx.json",
    "docker-compose.yml",
    "docker-compose.yaml",
)


def resolve_main_repo(git: GitConfig) -> str | None:
    """Return resolved main repo slug, or None if not configured."""
    raw = (git.main_repo or "").strip()
    if not raw:
        return None
    try:
        return resolve_repo_slug(raw, git)
    except ValueError:
        if "/" in raw:
            return raw.strip("/")
        return None


def shared_mirror_path(data_dir: Path, repo_slug: str) -> Path:
    return shared_repos_dir(data_dir) / repo_slug.replace("/", "__")


def read_context_manifest(data_dir: Path, repo_slug: str) -> dict[str, Any] | None:
    path = repo_context_dir(data_dir, repo_slug) / MANIFEST_NAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def context_status(data_dir: Path, git: GitConfig, *, ai: AIConfig | None = None) -> dict[str, Any]:
    """Summary for admin UI."""
    main = resolve_main_repo(git)
    if not main:
        return {
            "main_repo": "",
            "configured": False,
            "generated_at": None,
            "head_sha": None,
            "files": [],
            "mirror_present": False,
            "graphify_enabled": git.graphify_enabled,
        }

    out_dir = repo_context_dir(data_dir, main)
    manifest = read_context_manifest(data_dir, main) or {}
    files = sorted(
        p.name for p in out_dir.iterdir() if p.is_file() and p.suffix == ".md"
    ) if out_dir.is_dir() else []
    mirror = shared_mirror_path(data_dir, main)
    from backend.context.graphify import graph_status

    graph = graph_status(data_dir, git, ai=ai)
    return {
        "main_repo": main,
        "configured": True,
        "generated_at": manifest.get("generated_at"),
        "head_sha": manifest.get("head_sha"),
        "files": files,
        "mirror_present": mirror.is_dir() and any(mirror.iterdir()),
        "graphify_enabled": git.graphify_enabled,
        "graph": graph,
    }


def generate_repo_context(
    data_dir: Path,
    git: GitConfig,
    *,
    repo: str | None = None,
    ai: AIConfig | None = None,
    run_graphify: bool = True,
) -> dict[str, Any]:
    """Scan shared mirror and write .alfred/context/{repo}/ overview + layout MD."""
    slug = resolve_repo_slug(repo or git.main_repo or "", git) if (repo or git.main_repo) else None
    if not slug:
        raise ValueError("main_repo is not configured")

    mirror = shared_mirror_path(data_dir, slug)
    if not mirror.is_dir() or not any(mirror.iterdir()):
        raise FileNotFoundError(
            f"Shared mirror for {slug!r} is missing — sync it first (alfred git sync)."
        )

    head_sha = _head_sha(mirror)
    out_dir = repo_context_dir(data_dir, slug)
    overview = _build_overview(slug, mirror, head_sha)
    layout = _build_layout(mirror)

    (out_dir / OVERVIEW_NAME).write_text(overview, encoding="utf-8")
    (out_dir / LAYOUT_NAME).write_text(layout, encoding="utf-8")

    manifest = {
        "repo": slug,
        "head_sha": head_sha,
        "generated_at": _now_iso(),
        "files": [OVERVIEW_NAME, LAYOUT_NAME],
        "graphify_enabled": git.graphify_enabled,
    }
    (out_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    logger.info("Generated repo context for %s at %s", slug, out_dir)

    graph_result: dict[str, Any] | None = None
    if run_graphify and git.graphify_enabled:
        from backend.context.graphify import extract_graph

        graph_result = extract_graph(data_dir, git, repo=slug, ai=ai)
        manifest["graphify"] = graph_result
        if graph_result.get("ok"):
            manifest["graphify"]["present"] = True
        (out_dir / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )

    suggestions_result: dict[str, Any] | None = None
    try:
        from backend.context.suggestions import generate_suggestions

        pending = generate_suggestions(data_dir, git)
        suggestions_result = {"ok": True, "pending_count": len(pending)}
        manifest["suggestions"] = suggestions_result
        (out_dir / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("Suggestion generation skipped for %s: %s", slug, exc)
        suggestions_result = {"ok": False, "error": str(exc)}

    return manifest


def load_repo_context_for_prompt(
    data_dir: Path,
    git: GitConfig,
    *,
    max_chars: int = MAX_PROMPT_CHARS,
) -> str:
    """Load generated MD for injection into the system prompt."""
    slug = resolve_main_repo(git)
    if not slug:
        return ""

    out_dir = repo_context_dir(data_dir, slug)
    parts: list[str] = []
    for name in (OVERVIEW_NAME, LAYOUT_NAME):
        path = out_dir / name
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8").strip())

    if not parts:
        return ""

    manifest = read_context_manifest(data_dir, slug) or {}
    header = [
        "## Main repository context",
        f"Repo: `{slug}`",
    ]
    if manifest.get("head_sha"):
        header.append(f"Indexed at commit: `{manifest['head_sha'][:12]}`")

    header.append(
        "Use this as background when answering questions about this codebase."
    )

    text = "\n\n".join([*header, "", *parts])
    if len(text) > max_chars:
        text = text[: max_chars - 20].rstrip() + "\n\n...(truncated)"
    return text


def _build_overview(repo: str, mirror: Path, head_sha: str | None) -> str:
    lines = [
        f"# {repo} — overview",
        "",
        "Auto-generated from the shared mirror on `main`. Edit playbooks for curated domain knowledge.",
        "",
    ]
    if head_sha:
        lines.append(f"- **HEAD:** `{head_sha[:12]}`")
    lines.append(f"- **Root:** `{mirror.name}`")

    readme = _read_readme(mirror)
    if readme:
        lines.extend(["", "## README excerpt", "", readme])

    key_notes = _summarize_key_files(mirror)
    if key_notes:
        lines.extend(["", "## Key manifests", ""])
        lines.extend(key_notes)

    return "\n".join(lines).strip() + "\n"


def _build_layout(mirror: Path) -> str:
    lines = [
        "# Repository layout",
        "",
        "Top-level directories and notable files (hidden/vendor dirs omitted).",
        "",
    ]

    entries = _list_top_level(mirror)
    if not entries:
        lines.append("_No top-level entries found._")
        return "\n".join(lines).strip() + "\n"

    dirs = [e for e in entries if e["kind"] == "dir"]
    files = [e for e in entries if e["kind"] == "file"]

    if dirs:
        lines.append("## Directories")
        lines.append("")
        for item in dirs:
            hint = _dir_hint(mirror / item["name"])
            suffix = f" — {hint}" if hint else ""
            lines.append(f"- `{item['name']}/`{suffix}")
        lines.append("")

    if files:
        lines.append("## Root files")
        lines.append("")
        for item in files[:30]:
            lines.append(f"- `{item['name']}`")

    monorepo_roots = _detect_monorepo_roots(mirror, dirs)
    if monorepo_roots:
        lines.extend(["", "## Likely monorepo roots", ""])
        for root in monorepo_roots:
            lines.append(f"- `{root}/`")

    return "\n".join(lines).strip() + "\n"


def _read_readme(mirror: Path) -> str:
    for name in ("README.md", "Readme.md", "readme.md"):
        path = mirror / name
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            if len(text) > MAX_README_CHARS:
                return text[:MAX_README_CHARS].rstrip() + "\n\n...(truncated)"
            return text
    return ""


def _summarize_key_files(mirror: Path) -> list[str]:
    notes: list[str] = []
    for name in _KEY_FILES:
        path = mirror / name
        if not path.is_file():
            continue
        if name == "package.json":
            notes.append(f"- `{name}` — Node/package manifest")
        elif name == "pyproject.toml":
            notes.append(f"- `{name}` — Python project config")
        elif name == "go.mod":
            first_line = path.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
            module = ""
            if first_line and first_line[0].startswith("module "):
                module = first_line[0][7:].strip()
            detail = f" ({module})" if module else ""
            notes.append(f"- `{name}`{detail}")
        elif name in ("pnpm-workspace.yaml", "turbo.json", "nx.json"):
            notes.append(f"- `{name}` — monorepo workspace config")
        else:
            notes.append(f"- `{name}`")
    return notes


def _list_top_level(mirror: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    try:
        for path in sorted(mirror.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if path.name in _SKIP_DIR_NAMES or path.name.startswith("."):
                continue
            rows.append({"name": path.name, "kind": "dir" if path.is_dir() else "file"})
    except OSError:
        return rows
    return rows


def _dir_hint(path: Path) -> str:
    if not path.is_dir():
        return ""
    child_dirs = [
        c.name
        for c in path.iterdir()
        if c.is_dir() and c.name not in _SKIP_DIR_NAMES and not c.name.startswith(".")
    ]
    if len(child_dirs) >= 3:
        preview = ", ".join(sorted(child_dirs)[:4])
        if len(child_dirs) > 4:
            preview += ", …"
        return preview
    py_count = sum(1 for _ in path.rglob("*.py") if "node_modules" not in str(_))
    ts_count = sum(
        1
        for _ in path.rglob("*.ts")
        if "node_modules" not in str(_) and "dist" not in str(_)
    )
    if py_count >= 5:
        return f"~{min(py_count, 999)} Python files"
    if ts_count >= 5:
        return f"~{min(ts_count, 999)} TypeScript files"
    return ""


def _detect_monorepo_roots(mirror: Path, dirs: list[dict[str, str]]) -> list[str]:
    names = {d["name"] for d in dirs}
    roots: list[str] = []
    for candidate in ("packages", "apps", "services", "libs", "modules"):
        if candidate in names:
            roots.append(candidate)
    workspace_file = mirror / "pnpm-workspace.yaml"
    if workspace_file.is_file():
        roots.append("pnpm-workspace.yaml")
    return roots


def _head_sha(repo_dir: Path) -> str | None:
    if not (repo_dir / ".git").exists():
        return None
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        return out.stdout.strip() or None
    except (subprocess.SubprocessError, OSError):
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
