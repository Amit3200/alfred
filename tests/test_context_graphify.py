"""Tests for Graphify integration."""

from __future__ import annotations
from backend.context.graphify import graphify_extract_lock
from backend.context.graphify import graph_summary


import json
from pathlib import Path
from unittest.mock import patch

from backend.context.graphify import (
    extract_graph,
    graph_json_path,
    graphify_out_dir,
    query_graph,
    resolve_graphify_llm,
)
from backend.models.config import AIConfig, AIProviderConfig, GitConfig


def _git_config(**overrides) -> GitConfig:
    base = dict(
        enabled=True,
        token="test",
        default_org="acme",
        repos=["acme/backend"],
        main_repo="acme/backend",
        graphify_enabled=True,
    )
    base.update(overrides)
    return GitConfig(**base)


def test_query_graph_reads_graph_json(tmp_path):
    git = _git_config()
    out = graphify_out_dir(tmp_path, "acme/backend")
    graph = {
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [{"source": "a", "target": "b"}],
    }
    (out / "graph.json").write_text(json.dumps(graph), encoding="utf-8")

    report = out / "GRAPH_REPORT.md"
    report.write_text("# God nodes\n- CheckoutService", encoding="utf-8")

    with patch("backend.context.graphify.resolve_graphify_command", return_value=None):
        result = query_graph(tmp_path, git, "what calls checkout?")

    assert result["ok"] is True
    assert "CheckoutService" in result["answer"]
    assert graph_json_path(tmp_path, "acme/backend") is not None


def test_extract_graph_skipped_when_disabled(tmp_path):
    git = _git_config(graphify_enabled=False)
    result = extract_graph(tmp_path, git)
    assert result.get("skipped") is True


def test_resolve_graphify_llm_uses_kimi_key_when_provider_disabled():
    ai = AIConfig(
        default_provider="kimi",
        routing={"investigation": "kimi"},
        providers={
            "ollama": AIProviderConfig(
                enabled=True,
                base_url="http://localhost:11434/v1",
                model="llama3.2:3b",
            ),
            "kimi": AIProviderConfig(
                enabled=False,
                api_key="sk-kimi-test",
                model="kimi-k2.6",
            ),
        },
    )
    _, _, provider = resolve_graphify_llm(ai)
    assert provider == "kimi"


def test_resolve_graphify_llm_prefers_kimi_over_default_ollama():
    ai = AIConfig(
        default_provider="ollama",
        routing={"investigation": "ollama"},
        providers={
            "ollama": AIProviderConfig(
                enabled=True,
                base_url="http://localhost:11434/v1",
                model="llama3",
            ),
            "kimi": AIProviderConfig(
                enabled=True,
                api_key="sk-kimi-test",
                model="kimi-k2.6",
            ),
        },
    )
    _, _, provider = resolve_graphify_llm(ai)
    assert provider == "kimi"


def test_resolve_graphify_llm_uses_investigation_kimi():
    ai = AIConfig(
        default_provider="ollama",
        routing={"investigation": "kimi"},
        providers={
            "kimi": AIProviderConfig(
                enabled=True,
                api_key="sk-kimi-test",
                base_url="https://api.moonshot.ai/v1",
                model="kimi-k2.6",
            ),
        },
    )
    args, env, provider = resolve_graphify_llm(ai)
    assert provider == "kimi"
    assert "--backend=kimi" in args
    assert "--model=kimi-k2.6" in args
    assert env["MOONSHOT_API_KEY"] == "sk-kimi-test"


def test_extract_graph_requires_llm_key(tmp_path, monkeypatch):
    git = _git_config()
    mirror = tmp_path / "repos" / "shared" / "acme__backend"
    mirror.mkdir(parents=True)
    (mirror / "README.md").write_text("# hi", encoding="utf-8")

    monkeypatch.setattr("backend.context.graphify.graphify_cli_available", lambda: True)
    monkeypatch.setattr(
        "backend.context.graphify.resolve_graphify_command",
        lambda: ["graphify"],
    )
    result = extract_graph(tmp_path, git, ai=AIConfig())
    assert result["ok"] is False
    assert "No LLM API key configured" in result["error"]


def test_extract_graph_passes_kimi_env(tmp_path, monkeypatch):
    git = _git_config()
    mirror = tmp_path / "repos" / "shared" / "acme__backend"
    mirror.mkdir(parents=True)
    (mirror / "README.md").write_text("# hi", encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_run(args, *, timeout, env=None):
        captured["args"] = args
        captured["env"] = env
        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr("backend.context.graphify.graphify_cli_available", lambda: True)
    monkeypatch.setattr(
        "backend.context.graphify.resolve_graphify_command",
        lambda: ["graphify"],
    )
    monkeypatch.setattr("backend.context.graphify._run_graphify", fake_run)
    monkeypatch.setattr("backend.context.graphify._relocate_graphify_output", lambda *a, **k: None)

    ai = AIConfig(
        routing={"investigation": "kimi"},
        providers={
            "kimi": AIProviderConfig(enabled=True, api_key="sk-kimi-test", model="kimi-k2.6"),
        },
    )
    result = extract_graph(tmp_path, git, ai=ai)
    assert result["ok"] is True
    assert captured["env"]["MOONSHOT_API_KEY"] == "sk-kimi-test"
    assert "--backend=kimi" in captured["args"]


def test_extract_graph_rejects_concurrent_run(tmp_path, monkeypatch):
    git = _git_config()
    mirror = tmp_path / "repos" / "shared" / "acme__backend"
    mirror.mkdir(parents=True)
    (mirror / "README.md").write_text("# hi", encoding="utf-8")

    monkeypatch.setattr("backend.context.graphify.graphify_cli_available", lambda: True)
    monkeypatch.setattr(
        "backend.context.graphify.resolve_graphify_command",
        lambda: ["graphify"],
    )

    ai = AIConfig(
        routing={"investigation": "kimi"},
        providers={"kimi": AIProviderConfig(enabled=True, api_key="sk-kimi", model="kimi-k2.6")},
    )

    pass

    with graphify_extract_lock(tmp_path, "acme/backend"):
        result = extract_graph(tmp_path, git, ai=ai)
    assert result["ok"] is False
    assert result.get("busy") is True


def test_extract_graph_requires_cli(tmp_path, monkeypatch):
    git = _git_config()
    mirror = tmp_path / "repos" / "shared" / "acme__backend"
    mirror.mkdir(parents=True)
    (mirror / "README.md").write_text("# hi", encoding="utf-8")

    monkeypatch.setattr("backend.context.graphify.resolve_graphify_command", lambda: None)
    result = extract_graph(tmp_path, git)
    assert result["ok"] is False
    assert "uv sync --extra graphify" in result["error"]


def test_graph_summary_counts_nodes(tmp_path):
    git = _git_config()
    out = graphify_out_dir(tmp_path, "acme/backend")
    graph = {
        "nodes": [
            {"id": "a", "label": "Alpha", "kind": "class"},
            {"id": "b", "label": "Beta", "kind": "function"},
        ],
        "edges": [{"source": "a", "target": "b", "kind": "calls"}],
    }
    (out / "graph.json").write_text(json.dumps(graph), encoding="utf-8")

    pass

    summary = graph_summary(tmp_path, "acme/backend")
    assert summary["present"] is True
    assert summary["node_count"] == 2
    assert summary["edge_count"] == 1
    assert summary["node_kinds"]["class"] == 1
    assert summary["top_nodes"][0]["label"] in {"Alpha", "Beta"}
