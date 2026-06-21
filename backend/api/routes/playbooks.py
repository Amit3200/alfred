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
from backend.ingress.playbooks import _parse_playbook
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
    safe = _safe_filename(filename)
    path = (root / safe).resolve()
    if path.parent != root.resolve():
        raise HTTPException(status_code=400, detail="Invalid filename")
    return path


def _iso_mtime(path: Path) -> str | None:
    try:
        ts = path.stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except OSError:
        return None


def _metadata_for(path: Path) -> dict[str, Any]:
    row: dict[str, Any] = {
        "filename": path.name,
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
    files = sorted(root.glob("*.md"), key=lambda p: p.name.lower())
    items = [_metadata_for(path) for path in files if path.name.lower() != "readme.md"]
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


@router.get("/{filename}")
def get_playbook(
    filename: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    root = _playbooks_root(manager)
    path = _resolve_path(root, filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Playbook {filename!r} not found")
    content = path.read_text(encoding="utf-8")
    return {"filename": path.name, "content": content, **_metadata_for(path)}


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
    path.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
    return {"ok": True, "filename": path.name, **_metadata_for(path)}


@router.put("/{filename}")
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
    return {"ok": True, "filename": path.name, **_metadata_for(path)}


@router.delete("/{filename}")
def delete_playbook(
    filename: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    root = _playbooks_root(manager)
    path = _resolve_path(root, filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Playbook {filename!r} not found")
    path.unlink()
    return {"ok": True, "removed": path.name}
