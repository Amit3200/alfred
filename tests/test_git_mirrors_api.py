"""Tests for git mirror admin API."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.config_manager import ConfigManager
from backend.git.mirror import WorkspaceMirrorManager
from backend.models.config import GitConfig


def _client(tmp_path) -> tuple[TestClient, str, ConfigManager]:
    manager = ConfigManager(tmp_path)
    manager.init()
    config, secrets = manager.load_merged()
    config.git = GitConfig(enabled=True, provider="github", token="ghp_test")
    manager.save_merged(config, secrets)
    admin_token = secrets.server_admin_token or "test-admin-token"
    app = create_app(tmp_path)
    return TestClient(app), admin_token, manager


def _seed_workspace(manager: ConfigManager, workspace_id: str) -> None:
    config, _ = manager.load_merged()
    mirror = WorkspaceMirrorManager(config.git, manager.data_dir)
    path = mirror.workspaces_root / workspace_id
    path.mkdir(parents=True)
    stale = datetime.now(timezone.utc) - timedelta(hours=48)
    manifest = {
        "session_key": f"ui:{workspace_id}",
        "last_used_at": stale.isoformat(),
        "repos": {"org/repo": {"ref": "main"}},
    }
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (path / "org__repo").mkdir()
    (path / "org__repo" / "file.txt").write_text("hello", encoding="utf-8")


def test_get_mirrors_lists_workspaces(tmp_path):
    client, admin_token, manager = _client(tmp_path)
    headers = {"X-Alfred-Token": admin_token}
    _seed_workspace(manager, "ui_test_chat")

    res = client.get("/api/git/mirrors", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is True
    assert data["summary"]["workspaces_count"] == 1
    assert data["workspaces"][0]["repos"] == ["org/repo"]


def test_cleanup_all_workspaces(tmp_path):
    client, admin_token, manager = _client(tmp_path)
    headers = {"X-Alfred-Token": admin_token}
    _seed_workspace(manager, "ui_test_chat")

    res = client.post(
        "/api/git/mirrors/cleanup",
        headers=headers,
        json={"scope": "workspaces"},
    )
    assert res.status_code == 200
    body = res.json()
    assert "ui_test_chat" in body["removed_workspaces"]
    assert body["summary"]["workspaces_count"] == 0


def test_list_available_repos_api(tmp_path):
    client, admin_token, manager = _client(tmp_path)
    headers = {"X-Alfred-Token": admin_token}
    config, secrets = manager.load_merged()
    config.git = GitConfig(
        enabled=True,
        provider="github",
        token="ghp_test",
        default_org="FlexyPe",
        repos=["FlexyPe/cipher"],
    )
    manager.save_merged(config, secrets)

    from unittest.mock import patch

    with patch("backend.git.api._GitHubClient.list_accessible_repos") as mock_list:
        mock_list.return_value = ["FlexyPe/cipher", "FlexyPe/other"]
        res = client.get("/api/git/mirrors/repos/available", headers=headers)

    assert res.status_code == 200
    body = res.json()
    assert body["source"] == "org"
    assert "FlexyPe/other" in body["repos"]
