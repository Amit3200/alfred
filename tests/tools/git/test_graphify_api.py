"""Tests for Graphify admin API."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.config_manager import ConfigManager
from backend.context.graphify import graphify_out_dir
from backend.models.config import GitConfig
from backend.paths import repo_context_dir


def _client(tmp_path) -> tuple[TestClient, str, ConfigManager]:
    manager = ConfigManager(tmp_path)
    manager.init()
    config, secrets = manager.load_merged()
    config.git = GitConfig(
        enabled=True,
        provider="github",
        token="ghp_test",
        default_org="acme",
        repos=["acme/backend"],
        main_repo="acme/backend",
        graphify_enabled=True,
    )
    manager.save_merged(config, secrets)
    admin_token = secrets.server_admin_token or "test-admin-token"
    app = create_app(tmp_path)
    return TestClient(app), admin_token, manager


def _seed_mirror_and_graph(manager: ConfigManager) -> None:
    data_dir = manager.data_dir
    mirror = data_dir / "repos" / "shared" / "acme__backend"
    mirror.mkdir(parents=True)
    (mirror / "README.md").write_text("# backend", encoding="utf-8")

    out = graphify_out_dir(data_dir, "acme/backend")
    graph = {
        "nodes": [
            {"id": "a", "label": "Alpha", "kind": "class"},
            {"id": "b", "label": "Beta", "kind": "function"},
        ],
        "edges": [{"source": "a", "target": "b", "kind": "calls"}],
    }
    (out / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (out / "GRAPH_REPORT.md").write_text("# God nodes\n- Alpha", encoding="utf-8")

    ctx_dir = repo_context_dir(data_dir, "acme/backend")
    (ctx_dir / "manifest.json").write_text(
        json.dumps(
            {
                "repo": "acme/backend",
                "graphify": {"ok": True, "rebuilt_at": "2026-06-21T12:00:00+00:00"},
            }
        ),
        encoding="utf-8",
    )


def test_graphify_status_api(tmp_path):
    client, admin_token, manager = _client(tmp_path)
    headers = {"X-Alfred-Token": admin_token}
    _seed_mirror_and_graph(manager)

    res = client.get("/api/repo-context/graphify", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["enabled"] is True
    assert body["present"] is True
    assert body["node_count"] == 2
    assert body["report_present"] is True
    assert body["summary"]["top_nodes"]


def test_graphify_report_api(tmp_path):
    client, admin_token, manager = _client(tmp_path)
    headers = {"X-Alfred-Token": admin_token}
    _seed_mirror_and_graph(manager)

    res = client.get("/api/repo-context/graphify/report", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["present"] is True
    assert "Alpha" in body["content"]


def test_graphify_report_synthetic_without_cluster_report(tmp_path):
    client, admin_token, manager = _client(tmp_path)
    headers = {"X-Alfred-Token": admin_token}
    _seed_mirror_and_graph(manager)
    out = graphify_out_dir(manager.data_dir, "acme/backend")
    (out / "GRAPH_REPORT.md").unlink()

    res = client.get("/api/repo-context/graphify/report", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["present"] is True
    assert body["synthetic"] is True
    assert "Graph summary" in body["content"]
    assert "Alpha" in body["content"]


def test_graphify_rebuild_requires_cli(tmp_path, monkeypatch):
    client, admin_token, manager = _client(tmp_path)
    headers = {"X-Alfred-Token": admin_token}
    mirror = manager.data_dir / "repos" / "shared" / "acme__backend"
    mirror.mkdir(parents=True)
    (mirror / "README.md").write_text("# hi", encoding="utf-8")

    monkeypatch.setattr("backend.context.graphify.resolve_graphify_command", lambda: None)

    res = client.post("/api/repo-context/graphify/rebuild", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert "uv sync --extra graphify" in body["result"]["error"]
