"""Admin API for local domain playbooks (`.alfred/playbooks/*.md`)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.deps import require_admin
from backend.config_manager import ConfigManager
from backend.routing.playbook_store_registry import invalidate_playbook_store
from backend.routing.playbooks import _parse_playbook
from backend.paths import bundled_playbooks_dir, playbooks_dir

router = APIRouter(prefix="/playbooks", tags=["playbooks"])

_FILENAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*\.md$")
_MAX_BYTES = 512 * 1024


class PlaybookWriteBody(BaseModel):
    content: str = Field(..., min_length=1)


class PlaybookCreateBody(BaseModel):
    filename: str = Field(..., min_length=1)
    content: str = Field(default="")


def _playbooks_root(manager: ConfigManager) -> Path:
    root = playbooks_dir(manager.data_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_filename(raw: str) -> str:
    name = Path(raw.strip()).name
    if not name.lower().endswith(".md"):
        name = f"{name}.md"
    if name.lower() == "readme.md":
        raise HTTPException(status_code=400, detail="readme.md is reserved")
    if not _FILENAME_RE.match(name):
        raise HTTPException(
            status_code=400,
            detail="Filename must be alphanumeric (hyphens/underscores allowed) and end with .md",
        )
    return name


def _resolve_path(root: Path, filename: str) -> Path:
    safe = Path(filename.strip()).as_posix().lstrip("/")
    if ".." in safe.split("/"):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if safe.lower() == "readme.md":
        raise HTTPException(status_code=400, detail="readme.md is reserved")
    parts = [p for p in safe.split("/") if p]
    if not parts:
        raise HTTPException(status_code=400, detail="Invalid filename")
    leaf = parts[-1]
    if not leaf.lower().endswith(".md"):
        leaf = f"{leaf}.md"
        parts[-1] = leaf
    if not _FILENAME_RE.match(leaf):
        raise HTTPException(
            status_code=400,
            detail="Filename must be alphanumeric (hyphens/underscores allowed) and end with .md",
        )
    path = (root.joinpath(*parts)).resolve()
    if path.parent != root.resolve() and root.resolve() not in path.parents:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return path


def _playbook_relative_name(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _iso_mtime(path: Path) -> str | None:
    try:
        ts = path.stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except OSError:
        return None


def _metadata_for(root: Path, path: Path) -> dict[str, Any]:
    row: dict[str, Any] = {
        "filename": _playbook_relative_name(root, path),
        "size_bytes": path.stat().st_size,
        "updated_at": _iso_mtime(path),
    }
    try:
        playbook = _parse_playbook(path, bundled=False)
        row["name"] = playbook.name
        row["triggers"] = playbook.triggers
        row["mode"] = playbook.mode
        row["channels"] = playbook.channels
        row["fetch_urls"] = playbook.fetch_urls
        row["fetch_ttl_minutes"] = playbook.fetch_ttl_minutes
    except Exception as exc:
        row["parse_error"] = str(exc)
    return row


def _default_new_playbook(filename: str) -> str:
    stem = Path(filename).stem
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-") or "playbook"
    return f"""---
name: {slug}
triggers:
  - example-trigger
channels: []
---

# {stem.replace("-", " ").replace("_", " ").title()}

Add your company-specific instructions here.
"""


@router.get("")
def list_playbooks(manager: ConfigManager = Depends(require_admin)) -> dict[str, Any]:
    root = _playbooks_root(manager)
    files = sorted(root.rglob("*.md"), key=lambda p: p.as_posix().lower())
    items = [
        _metadata_for(root, path)
        for path in files
        if path.name.lower() != "readme.md"
    ]
    example = bundled_playbooks_dir() / "example-slack-summaries.md"
    return {
        "directory": str(root),
        "playbooks": items,
        "example_available": example.is_file(),
    }


@router.get("/example")
def get_example_playbook(manager: ConfigManager = Depends(require_admin)) -> dict[str, str]:
    example = bundled_playbooks_dir() / "example-slack-summaries.md"
    if not example.is_file():
        raise HTTPException(status_code=404, detail="Example playbook not found")
    return {"filename": "slack-summaries.md", "content": example.read_text(encoding="utf-8")}


@router.get("/pending")
def list_pending_playbooks_route(
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    from backend.orchestrator.playbook_pending import list_pending_playbooks

    pending = list_pending_playbooks(manager.data_dir)
    return {"pending": pending, "total": len(pending)}


@router.get("/pending/{pending_id}")
def get_pending_playbook_route(
    pending_id: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    from backend.orchestrator.playbook_pending import get_pending_playbook

    try:
        item = get_pending_playbook(manager.data_dir, pending_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"pending": item}


@router.post("/pending/{pending_id}/approve")
def approve_pending_playbook_route(
    pending_id: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    from backend.orchestrator.playbook_pending import approve_pending_playbook

    try:
        result = approve_pending_playbook(manager.data_dir, pending_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    invalidate_playbook_store(manager.data_dir)
    return result


@router.post("/pending/{pending_id}/reject")
def reject_pending_playbook_route(
    pending_id: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    from backend.orchestrator.playbook_pending import reject_pending_playbook

    try:
        return reject_pending_playbook(manager.data_dir, pending_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{filename:path}")
def get_playbook(
    filename: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    root = _playbooks_root(manager)
    path = _resolve_path(root, filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Playbook {filename!r} not found")
    content = path.read_text(encoding="utf-8")
    return {"filename": _playbook_relative_name(root, path), "content": content, **_metadata_for(root, path)}


@router.post("")
def create_playbook(
    body: PlaybookCreateBody,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    root = _playbooks_root(manager)
    path = _resolve_path(root, body.filename)
    if path.is_file():
        raise HTTPException(status_code=409, detail=f"Playbook {path.name!r} already exists")
    content = body.content.strip() or _default_new_playbook(path.name)
    encoded = content.encode("utf-8")
    if len(encoded) > _MAX_BYTES:
        raise HTTPException(status_code=400, detail="Playbook exceeds 512 KB limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
    invalidate_playbook_store(manager.data_dir)
    return {"ok": True, "filename": _playbook_relative_name(root, path), **_metadata_for(root, path)}


@router.put("/{filename:path}")
def save_playbook(
    filename: str,
    body: PlaybookWriteBody,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    root = _playbooks_root(manager)
    path = _resolve_path(root, filename)
    encoded = body.content.encode("utf-8")
    if len(encoded) > _MAX_BYTES:
        raise HTTPException(status_code=400, detail="Playbook exceeds 512 KB limit")
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")
    path.write_text(
        body.content if body.content.endswith("\n") else body.content + "\n",
        encoding="utf-8",
    )
    invalidate_playbook_store(manager.data_dir)
    return {"ok": True, "filename": _playbook_relative_name(root, path), **_metadata_for(root, path)}


@router.delete("/{filename:path}")
def delete_playbook(
    filename: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    root = _playbooks_root(manager)
    path = _resolve_path(root, filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Playbook {filename!r} not found")
    path.unlink()
    invalidate_playbook_store(manager.data_dir)
    return {"ok": True, "removed": _playbook_relative_name(root, path)}
