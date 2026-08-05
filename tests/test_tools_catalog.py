"""Tests for tool catalog listing (CLI + API)."""

from __future__ import annotations

from pathlib import Path

from backend.models.config import AlfredConfig, GitConfig, JiraConfig
from backend.tools.list_catalog import build_tools_catalog, format_tools_cli


def test_build_tools_catalog_enabled_counts():
    config = AlfredConfig(
        git=GitConfig(enabled=True, provider="github", token="t"),
        jira=JiraConfig(enabled=True, url="https://jira.example.com", email="a@b.com"),
    )
    catalog = build_tools_catalog(config, playbooks=[])
    assert catalog["summary"]["total"] >= 50
    assert catalog["summary"]["enabled"] > catalog["summary"]["total"] // 4
    git_domain = next(d for d in catalog["domains"] if d["name"] == "git")
    assert git_domain["enabled_count"] > 0


def test_format_tools_cli_domain_filter():
    config = AlfredConfig()
    catalog = build_tools_catalog(config, playbooks=[])
    text = format_tools_cli(catalog, domain="schedule")
    assert "Schedules" in text
    assert "list_schedules" in text
    assert "jira_search" not in text


def test_tools_api_route(tmp_path: Path):
    from fastapi.testclient import TestClient

    from backend.api.app import create_app
    from backend.config_manager import ConfigManager

    manager = ConfigManager(tmp_path)
    manager.init()
    _, secrets = manager.load_merged()
    token = secrets.server_admin_token or "test-admin-token"
    app = create_app(tmp_path)
    client = TestClient(app)
    res = client.get("/api/tools/catalog", headers={"X-Alfred-Token": token})
    assert res.status_code == 200
    data = res.json()
    assert data["summary"]["total"] > 0
    assert "tools" in data
    assert "domains" in data
