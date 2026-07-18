"""Tests for playbook admin API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.config_manager import ConfigManager
from backend.paths import playbooks_dir


def _client(tmp_path) -> tuple[TestClient, str]:
    manager = ConfigManager(tmp_path)
    manager.init()
    _, secrets = manager.load_merged()
    admin_token = secrets.server_admin_token or "test-admin-token"
    app = create_app(tmp_path)
    return TestClient(app), admin_token


def _headers(token: str) -> dict[str, str]:
    return {"X-Alfred-Token": token}


def test_playbooks_crud_and_upload(tmp_path) -> None:
    client, token = _client(tmp_path)
    h = _headers(token)

    listed = client.get("/api/playbooks", headers=h)
    assert listed.status_code == 200
    initial_count = len(listed.json()["playbooks"])

    created = client.post(
        "/api/playbooks",
        headers=h,
        json={"filename": "merchant-alerts.md", "content": ""},
    )
    assert created.status_code == 200
    assert created.json()["filename"] == "merchant-alerts.md"
    assert "triggers:" in client.get("/api/playbooks/merchant-alerts.md", headers=h).json()["content"]

    updated = client.put(
        "/api/playbooks/merchant-alerts.md",
        headers=h,
        json={
            "content": "---\nname: merchant-alerts\ntriggers:\n  - merchant\n---\n\n# Alerts\n",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["triggers"] == ["merchant"]

    imported = client.post(
        "/api/playbooks",
        headers=h,
        json={
            "filename": "uploaded.md",
            "content": "---\nname: uploaded\ntriggers:\n  - upload\n---\n\nBody\n",
        },
    )
    assert imported.status_code == 200
    assert imported.json()["filename"] == "uploaded.md"

    listed2 = client.get("/api/playbooks", headers=h)
    assert len(listed2.json()["playbooks"]) == initial_count + 2

    deleted = client.delete("/api/playbooks/merchant-alerts.md", headers=h)
    assert deleted.status_code == 200
    assert not (playbooks_dir(tmp_path) / "merchant-alerts.md").exists()


def test_playbooks_nested_path_crud(tmp_path) -> None:
    client, token = _client(tmp_path)
    h = _headers(token)

    nested_dir = playbooks_dir(tmp_path) / "backend" / "p0-critical-path"
    nested_dir.mkdir(parents=True)
    path = nested_dir / "debug_example.md"
    path.write_text(
        """---
name: debug_example
triggers:
  - example trigger
---

Nested playbook body.
""",
        encoding="utf-8",
    )

    listed = client.get("/api/playbooks", headers=h)
    assert listed.status_code == 200
    filenames = {item["filename"] for item in listed.json()["playbooks"]}
    assert "backend/p0-critical-path/debug_example.md" in filenames

    fetched = client.get(
        "/api/playbooks/backend/p0-critical-path/debug_example.md",
        headers=h,
    )
    assert fetched.status_code == 200
    assert "Nested playbook body." in fetched.json()["content"]


def test_playbooks_rejects_invalid_filename(tmp_path) -> None:
    client, token = _client(tmp_path)
    h = _headers(token)

    bad = client.post("/api/playbooks", headers=h, json={"filename": "bad name.md", "content": "x"})
    assert bad.status_code == 400

    no_auth = client.get("/api/playbooks")
    assert no_auth.status_code == 401
