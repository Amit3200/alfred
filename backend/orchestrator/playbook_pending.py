"""Pending queue for self-learning and other auto-generated playbooks."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.models.task import Task
from backend.paths import get_data_dir, playbooks_dir

PENDING_FILENAME = "pending_playbooks.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _pending_path(data_dir: Path | None) -> Path:
    return get_data_dir(data_dir) / PENDING_FILENAME


def load_pending_playbooks(data_dir: Path | None = None) -> list[dict[str, Any]]:
    path = _pending_path(data_dir)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    except (OSError, json.JSONDecodeError):
        pass
    return []


def save_pending_playbooks(data_dir: Path | None, items: list[dict[str, Any]]) -> None:
    path = _pending_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2), encoding="utf-8")


def list_pending_playbooks(data_dir: Path | None = None) -> list[dict[str, Any]]:
    return [item for item in load_pending_playbooks(data_dir) if item.get("status") == "pending"]


def get_pending_playbook(data_dir: Path | None, pending_id: str) -> dict[str, Any]:
    match = next((item for item in load_pending_playbooks(data_dir) if item.get("id") == pending_id), None)
    if match is None:
        raise KeyError(f"Pending playbook {pending_id!r} not found")
    return match


def _safe_playbook_filename(name: str) -> str:
    stem = re.sub(r"[^a-z0-9_-]+", "", name.lower()).strip("_-") or "learned_playbook"
    return f"{stem}.md"


def enqueue_pending_playbook(
    *,
    task: Task,
    proposed_content: str,
    playbook_name: str,
    data_dir: Path | None = None,
) -> str:
    """Queue a generated playbook for admin review. Returns pending id."""
    filename = _safe_playbook_filename(playbook_name)
    items = load_pending_playbooks(data_dir)
    for item in items:
        if item.get("status") == "pending" and item.get("playbook_filename") == filename:
            item["proposed_content"] = proposed_content
            item["updated_at"] = _now_iso()
            item["source_task_id"] = task.id
            item["source_intent"] = task.cleaned_intent
            item["source_channel_id"] = task.channel_id
            save_pending_playbooks(data_dir, items)
            return str(item["id"])

    pending_id = str(uuid.uuid4())
    items.append(
        {
            "id": pending_id,
            "kind": "meta_learning",
            "title": f"Learned: {playbook_name.replace('_', ' ')}",
            "description": f"From task {task.id[:8]} — {task.cleaned_intent[:160]}",
            "playbook_filename": filename,
            "playbook_name": playbook_name,
            "proposed_content": proposed_content,
            "status": "pending",
            "created_at": _now_iso(),
            "source_task_id": task.id,
            "source_intent": task.cleaned_intent,
            "source_channel_id": task.channel_id,
            "source": task.source,
        }
    )
    save_pending_playbooks(data_dir, items)
    return pending_id


def approve_pending_playbook(data_dir: Path | None, pending_id: str) -> dict[str, Any]:
    items = load_pending_playbooks(data_dir)
    match = next((item for item in items if item.get("id") == pending_id), None)
    if match is None:
        raise KeyError(f"Pending playbook {pending_id!r} not found")
    if match.get("status") != "pending":
        raise ValueError(f"Pending playbook {pending_id!r} is not pending")

    filename = str(match.get("playbook_filename") or "").strip()
    content = str(match.get("proposed_content") or "").strip()
    if not filename or not content:
        raise ValueError("Pending playbook is missing filename or content")

    root = playbooks_dir(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / Path(filename).name
    if path.is_file():
        raise FileExistsError(f"Playbook {path.name!r} already exists — edit or delete it first.")

    path.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
    match["status"] = "approved"
    match["approved_at"] = _now_iso()
    match["playbook_path"] = str(path)
    save_pending_playbooks(data_dir, items)
    return {"ok": True, "filename": path.name, "pending": match}


def reject_pending_playbook(data_dir: Path | None, pending_id: str) -> dict[str, Any]:
    items = load_pending_playbooks(data_dir)
    match = next((item for item in items if item.get("id") == pending_id), None)
    if match is None:
        raise KeyError(f"Pending playbook {pending_id!r} not found")
    match["status"] = "rejected"
    match["rejected_at"] = _now_iso()
    save_pending_playbooks(data_dir, items)
    return {"ok": True, "pending": match}
