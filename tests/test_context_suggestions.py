"""Tests for playbook suggestions from repo context."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from backend.context.generator import generate_repo_context
from backend.context.suggestions import (
    approve_suggestion,
    dismiss_suggestion,
    generate_suggestions,
    list_pending_suggestions,
)
from backend.models.config import GitConfig
from backend.paths import playbooks_dir


def _git_config() -> GitConfig:
    return GitConfig(
        enabled=True,
        token="test",
        default_org="acme",
        repos=["acme/backend"],
        main_repo="acme/backend",
    )


def _seed_context(tmp_path: Path) -> None:
    fixture = Path(__file__).resolve().parent / "fixtures" / "sample-repo"
    mirror = tmp_path / "repos" / "shared" / "acme__backend"
    shutil.copytree(fixture, mirror)
    git = _git_config()
    generate_repo_context(tmp_path, git, repo="acme/backend")
    layout = tmp_path / "context" / "acme__backend" / "layout.md"
    layout.write_text(
        layout.read_text(encoding="utf-8")
        + "\n## Likely monorepo roots\n\n- `packages/`\n",
        encoding="utf-8",
    )


def test_generate_suggestions_creates_pending(tmp_path):
    _seed_context(tmp_path)
    git = _git_config()
    pending = generate_suggestions(tmp_path, git)
    assert len(pending) >= 2
    kinds = {s["kind"] for s in pending}
    assert "architecture" in kinds
    assert "modules" in kinds


def test_approve_suggestion_writes_playbook(tmp_path):
    _seed_context(tmp_path)
    git = _git_config()
    pending = generate_suggestions(tmp_path, git)
    suggestion = next(s for s in pending if s["kind"] == "architecture")
    result = approve_suggestion(tmp_path, git, suggestion["id"])
    path = playbooks_dir(tmp_path) / result["filename"]
    assert path.is_file()
    assert "architecture" in path.read_text(encoding="utf-8").lower()
    remaining = list_pending_suggestions(tmp_path, git)
    assert all(s["kind"] != "architecture" for s in remaining)


def test_dismiss_suggestion(tmp_path):
    _seed_context(tmp_path)
    git = _git_config()
    pending = generate_suggestions(tmp_path, git)
    dismiss_suggestion(tmp_path, git, pending[0]["id"])
    remaining = list_pending_suggestions(tmp_path, git)
    assert len(remaining) == len(pending) - 1


def test_approve_conflict_when_playbook_exists(tmp_path):
    _seed_context(tmp_path)
    git = _git_config()
    pending = generate_suggestions(tmp_path, git)
    filename = pending[0]["playbook_filename"]
    path = playbooks_dir(tmp_path)
    path.mkdir(parents=True, exist_ok=True)
    (path / filename).write_text("# existing\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        approve_suggestion(tmp_path, git, pending[0]["id"])
