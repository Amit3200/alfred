"""Tests for company script admin API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.config_manager import ConfigManager
from backend.paths import company_scripts_dir


def _client(tmp_path) -> tuple[TestClient, str]:
    manager = ConfigManager(tmp_path)
    manager.init()
    _, secrets = manager.load_merged()
    admin_token = secrets.server_admin_token or "test-admin-token"
    app = create_app(tmp_path)
    return TestClient(app), admin_token


def _headers(token: str) -> dict[str, str]:
    return {"X-Alfred-Token": token}


def test_scripts_package_crud(tmp_path) -> None:
    client, token = _client(tmp_path)
    h = _headers(token)

    listed = client.get("/api/scripts", headers=h)
    assert listed.status_code == 200
    assert "packages" in listed.json()

    created = client.post(
        "/api/scripts/packages",
        headers=h,
        json={
            "package_path": "ops/nightly_report",
            "runtime": "python3",
            "description": "Nightly rollup",
            "entry": "main.py",
        },
    )
    assert created.status_code == 200
    package = created.json()["package"]
    assert package["name"] == "ops/nightly_report"
    assert package["runtime"] == "python3"
    assert "script.yaml" in package["files"]

    manifest_path = "ops/nightly_report/script.yaml"
    fetched = client.get(f"/api/scripts/files/{manifest_path}", headers=h)
    assert fetched.status_code == 200
    assert "name: ops/nightly_report" in fetched.json()["content"]

    helper_path = "ops/nightly_report/lib/helpers.py"
    added = client.post(
        f"/api/scripts/files/{helper_path}",
        headers=h,
        json={"relative_path": helper_path, "content": "def helper():\n    return True\n"},
    )
    assert added.status_code == 200

    listed2 = client.get("/api/scripts", headers=h)
    names = {item["name"] for item in listed2.json()["packages"]}
    assert "ops/nightly_report" in names

    deleted = client.delete("/api/scripts/packages/ops/nightly_report", headers=h)
    assert deleted.status_code == 200
    assert not (company_scripts_dir(tmp_path) / "ops" / "nightly_report").exists()


def test_scripts_rejects_unauthenticated(tmp_path) -> None:
    client, _ = _client(tmp_path)
    assert client.get("/api/scripts").status_code == 401
