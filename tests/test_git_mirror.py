"""Tests for session-scoped mirror workspaces."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.integrations.git.mirror import WorkspaceMirrorManager, workspace_dir_name
from backend.models.config import GitConfig


def _git_config() -> GitConfig:
    return GitConfig(
        enabled=True,
        provider="github",
        token="test",
        repos=["acme/backend"],
        mirror_ttl_hours=24,
        mirror_max_workspaces=2,
    )


def test_workspace_dir_name_sanitizes_session_key():
    assert workspace_dir_name("slack:C1:1234.5") == "slack_C1_1234.5"


def test_cleanup_expired_removes_old_workspace(tmp_path):
    manager = WorkspaceMirrorManager(_git_config(), tmp_path)
    old = manager.workspaces_root / "old_ws"
    old.mkdir(parents=True)
    stale = datetime.now(timezone.utc) - timedelta(hours=48)
    manifest = {
        "session_key": "slack:C:1",
        "last_used_at": stale.isoformat(),
        "repos": {},
    }
    (old / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    removed = manager.cleanup_expired()
    assert "old_ws" in removed
    assert not old.exists()


def test_seed_workspace_from_shared_copy(tmp_path):
    fixture = Path(__file__).resolve().parent / "fixtures" / "sample-repo"
    manager = WorkspaceMirrorManager(_git_config(), tmp_path)

    shared_dest = manager.shared_root / "acme__backend"
    shutil.copytree(fixture, shared_dest)

    state = manager.ensure_repo("ui:chat1:chat1", "acme/backend")
    assert state.path.is_dir()
    assert (state.path / "order_handler.py").is_file()
    assert "duplicate order" in (state.path / "order_handler.py").read_text(encoding="utf-8")

    # Same session reuses workspace without error
    again = manager.ensure_repo("ui:chat1:chat1", "acme/backend")
    assert again.path == state.path


def test_pull_skips_local_only_feature_branch(tmp_path: Path):
    import os
    import subprocess

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }

    bare = tmp_path / "remote.git"
    bare.mkdir()
    subprocess.run(["git", "init", "--bare", "-b", "dev"], cwd=bare, check=True, capture_output=True, env=env)
    workspace = tmp_path / "workspace"
    repo = workspace / "acme__backend"
    subprocess.run(["git", "clone", str(bare), str(repo)], check=True, capture_output=True, env=env)
    subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True, capture_output=True, env=env)
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(["git", "push", "-u", "origin", "dev"], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(["git", "checkout", "-b", "alfred/pr/local-only"], cwd=repo, check=True, capture_output=True, env=env)
    (repo / "feature.txt").write_text("local\n", encoding="utf-8")
    subprocess.run(["git", "add", "feature.txt"], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "local work"], cwd=repo, check=True, capture_output=True, env=env)

    manager = WorkspaceMirrorManager(_git_config(), tmp_path)
    ws = manager.workspaces_root / workspace_dir_name("ui:chat1:chat1")
    ws.mkdir(parents=True, exist_ok=True)
    shutil.copytree(repo, ws / "acme__backend", dirs_exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    manifest = {
        "session_key": "ui:chat1:chat1",
        "last_used_at": now,
        "repos": {
            "acme/backend": {
                "ref": "alfred/pr/local-only",
                "last_pulled_at": "2020-01-01T00:00:00+00:00",
            }
        },
    }
    (ws / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    state = manager.ensure_repo("ui:chat1:chat1", "acme/backend")
    assert state.path.is_dir()
    assert (state.path / "feature.txt").is_file()
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=state.path,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout.strip()
    assert branch == "alfred/pr/local-only"


def test_different_sessions_get_isolated_copies(tmp_path):
    fixture = Path(__file__).resolve().parent / "fixtures" / "sample-repo"
    manager = WorkspaceMirrorManager(_git_config(), tmp_path)
    shared_dest = manager.shared_root / "acme__backend"
    shutil.copytree(fixture, shared_dest)

    a = manager.ensure_repo("ui:chatA:chatA", "acme/backend")
    b = manager.ensure_repo("ui:chatB:chatB", "acme/backend")
    assert a.path != b.path
    assert a.path.is_dir() and b.path.is_dir()


def test_cleanup_all_workspaces_and_shared(tmp_path):
    manager = WorkspaceMirrorManager(_git_config(), tmp_path)
    ws = manager.workspaces_root / "ws1"
    ws.mkdir(parents=True)
    (ws / "manifest.json").write_text("{}", encoding="utf-8")
    shared = manager.shared_root / "acme__backend"
    shared.mkdir(parents=True)
    (shared / "README.md").write_text("x", encoding="utf-8")

    removed_ws = manager.cleanup_all_workspaces()
    removed_sh = manager.cleanup_shared()
    assert "ws1" in removed_ws
    assert "acme__backend" in removed_sh
    assert manager.storage_summary()["total_bytes"] == 0
