"""Playbook enhancement suggestions from generated repo context."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.context.generator import (
    LAYOUT_NAME,
    OVERVIEW_NAME,
    read_context_manifest,
    repo_context_dir,
    resolve_main_repo,
)
from backend.models.config import GitConfig
from backend.paths import playbooks_dir

SUGGESTIONS_NAME = "suggestions.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _suggestions_path(data_dir: Path, repo_slug: str) -> Path:
    return repo_context_dir(data_dir, repo_slug) / SUGGESTIONS_NAME


def load_suggestions(data_dir: Path, repo_slug: str) -> list[dict[str, Any]]:
    path = _suggestions_path(data_dir, repo_slug)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    except (OSError, json.JSONDecodeError):
        pass
    return []


def save_suggestions(data_dir: Path, repo_slug: str, items: list[dict[str, Any]]) -> None:
    path = _suggestions_path(data_dir, repo_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2), encoding="utf-8")


def list_pending_suggestions(data_dir: Path, git: GitConfig) -> list[dict[str, Any]]:
    slug = resolve_main_repo(git)
    if not slug:
        return []
    return [s for s in load_suggestions(data_dir, slug) if s.get("status") == "pending"]


def generate_suggestions(data_dir: Path, git: GitConfig) -> list[dict[str, Any]]:
    """Build pending playbook suggestions from overview + layout MD."""
    slug = resolve_main_repo(git)
    if not slug:
        raise ValueError("main_repo is not configured")

    ctx_dir = repo_context_dir(data_dir, slug)
    overview_path = ctx_dir / OVERVIEW_NAME
    layout_path = ctx_dir / LAYOUT_NAME
    if not overview_path.is_file() or not layout_path.is_file():
        raise FileNotFoundError("Generate repo context first (overview.md + layout.md).")

    overview = overview_path.read_text(encoding="utf-8").strip()
    layout = layout_path.read_text(encoding="utf-8").strip()
    manifest = read_context_manifest(data_dir, slug) or {}
    repo_short = slug.rsplit("/", 1)[-1]
    slug_name = re.sub(r"[^a-z0-9]+", "-", repo_short.lower()).strip("-") or "repo"

    existing = {s.get("kind"): s for s in load_suggestions(data_dir, slug) if s.get("status") == "pending"}
    created: list[dict[str, Any]] = []

    arch_filename = f"{slug_name}-architecture.md"
    if "architecture" not in existing:
        created.append(
            _make_suggestion(
                kind="architecture",
                title=f"Architecture playbook for {slug}",
                description=(
                    "Curated overview of the main repo — README, layout, and key modules. "
                    "Approve to create a searchable playbook for basic codebase questions."
                ),
                playbook_filename=arch_filename,
                content=_build_architecture_playbook(
                    slug,
                    slug_name,
                    overview,
                    layout,
                    head_sha=manifest.get("head_sha"),
                ),
                head_sha=manifest.get("head_sha"),
            )
        )

    if "## Likely monorepo roots" in layout and "modules" not in existing:
        modules_filename = f"{slug_name}-modules.md"
        created.append(
            _make_suggestion(
                kind="modules",
                title=f"Monorepo modules map for {slug}",
                description=(
                    "Playbook derived from detected package roots and directory layout. "
                    "Helps answer which package owns what."
                ),
                playbook_filename=modules_filename,
                content=_build_modules_playbook(slug, slug_name, layout),
                head_sha=manifest.get("head_sha"),
            )
        )

    if not created:
        return list_pending_suggestions(data_dir, git)

    all_items = load_suggestions(data_dir, slug)
    pending_kinds = {s.get("kind") for s in all_items if s.get("status") == "pending"}
    for item in created:
        if item.get("kind") not in pending_kinds:
            all_items.append(item)
    save_suggestions(data_dir, slug, all_items)
    return list_pending_suggestions(data_dir, git)


def approve_suggestion(
    data_dir: Path,
    git: GitConfig,
    suggestion_id: str,
) -> dict[str, Any]:
    slug = resolve_main_repo(git)
    if not slug:
        raise ValueError("main_repo is not configured")

    items = load_suggestions(data_dir, slug)
    match = next((s for s in items if s.get("id") == suggestion_id), None)
    if not match:
        raise KeyError(f"Suggestion {suggestion_id!r} not found")
    if match.get("status") != "pending":
        raise ValueError(f"Suggestion {suggestion_id!r} is not pending")

    filename = str(match.get("playbook_filename") or "").strip()
    content = str(match.get("proposed_content") or "").strip()
    if not filename or not content:
        raise ValueError("Suggestion is missing playbook filename or content")

    root = playbooks_dir(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / Path(filename).name
    if path.is_file():
        raise FileExistsError(f"Playbook {path.name!r} already exists — edit or delete it first.")

    path.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
    match["status"] = "approved"
    match["approved_at"] = _now_iso()
    match["playbook_path"] = str(path)
    save_suggestions(data_dir, slug, items)
    return {"ok": True, "filename": path.name, "suggestion": match}


def dismiss_suggestion(data_dir: Path, git: GitConfig, suggestion_id: str) -> dict[str, Any]:
    slug = resolve_main_repo(git)
    if not slug:
        raise ValueError("main_repo is not configured")

    items = load_suggestions(data_dir, slug)
    match = next((s for s in items if s.get("id") == suggestion_id), None)
    if not match:
        raise KeyError(f"Suggestion {suggestion_id!r} not found")
    match["status"] = "dismissed"
    match["dismissed_at"] = _now_iso()
    save_suggestions(data_dir, slug, items)
    return {"ok": True, "suggestion": match}


def _make_suggestion(
    *,
    kind: str,
    title: str,
    description: str,
    playbook_filename: str,
    content: str,
    head_sha: str | None,
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "kind": kind,
        "title": title,
        "description": description,
        "playbook_filename": playbook_filename,
        "proposed_content": content,
        "status": "pending",
        "created_at": _now_iso(),
        "source_commit": head_sha,
    }


def _build_architecture_playbook(
    repo: str,
    slug_name: str,
    overview: str,
    layout: str,
    *,
    head_sha: str | None,
) -> str:
    commit_line = f"\nSource commit: `{head_sha[:12]}`" if head_sha else ""
    body = overview.replace("# ", "## ", 1) if overview.startswith("# ") else overview
    layout_body = layout.replace("# ", "## ", 1) if layout.startswith("# ") else layout
    return f"""---
name: {slug_name}-architecture
triggers:
  - {slug_name}
  - architecture
  - codebase
  - repo structure
  - main repo
  - {repo.split("/")[-1]}
channels: []
---

# {repo} — architecture context

Approved from auto-generated repo context.{commit_line}

Use this as **background knowledge** when users ask about how `{repo}` is organized. Cite paths from this doc; use git tools for live code.

{body}

---

{layout_body}
"""


def _build_modules_playbook(repo: str, slug_name: str, layout: str) -> str:
    section = ""
    if "## Likely monorepo roots" in layout:
        idx = layout.index("## Likely monorepo roots")
        section = layout[idx:].strip()

    return f"""---
name: {slug_name}-modules
triggers:
  - monorepo
  - packages
  - modules
  - {slug_name} modules
  - which package
channels: []
---

# {repo} — monorepo modules

Package and workspace layout for `{repo}`.

{section or layout}
"""
