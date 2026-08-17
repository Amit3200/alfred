"""Tests for mandatory doc Q&A bootstrap before agent loop."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.models.config import AlfredConfig, GitConfig, GitRepoProfile, RepoKnowledgeConfig
from backend.routing.doc_qa_bootstrap import bootstrap_doc_qa
from backend.tools.registry import ToolRegistry


@pytest.fixture
def docs_registry(tmp_path: Path, monkeypatch):
    empty_skills = tmp_path / "empty_skills"
    empty_skills.mkdir()
    monkeypatch.setattr("backend.routing.playbooks.bundled_skills_dir", lambda: empty_skills)
    monkeypatch.setattr("backend.context.doc_index._collect_playbook_docs", lambda _data_dir: [])

    from backend.context.doc_index import build_doc_index

    mirror = tmp_path / "repos" / "shared" / "FlexyPe__docs"
    (mirror / "handbook").mkdir(parents=True)
    (mirror / "handbook" / "mobile-app.mdx").write_text(
        "# Mobile app\n\nFlexyPe supports mobile app integration via SDK.\n",
        encoding="utf-8",
    )

    git = GitConfig(
        enabled=True,
        default_org="FlexyPe",
        main_repo="FlexyPe/cipher",
        repo_profiles=[GitRepoProfile(repo="FlexyPe/docs", role="docs")],
    )
    config = AlfredConfig(git=git, repo_knowledge=RepoKnowledgeConfig(enabled=True))
    build_doc_index(tmp_path, git, repo="FlexyPe/docs", alfred_config=config)

    from backend.tools.repo_docs import register_repo_doc_tools

    registry = ToolRegistry()
    register_repo_doc_tools(registry, config, data_dir=tmp_path)
    registry.git_config = git
    return registry, git


def test_bootstrap_records_search_in_trace(docs_registry):
    registry, git = docs_registry
    text = bootstrap_doc_qa(
        registry,
        query="do we support integration with mobile app?",
        allowed=["search_repo_docs", "read_repo_doc"],
        session=None,
        git=git,
    )
    assert "search_repo_docs" in text
    assert any(item.get("tool") == "search_repo_docs" for item in registry.tool_trace)
    assert registry.tool_trace[0]["success"] is True


def test_bootstrap_reads_matching_doc(docs_registry):
    registry, git = docs_registry
    bootstrap_doc_qa(
        registry,
        query="mobile app integration",
        allowed=["search_repo_docs", "read_repo_doc"],
        session=None,
        git=git,
    )
    tools = [item.get("tool") for item in registry.tool_trace]
    assert "search_repo_docs" in tools
    assert "read_repo_doc" in tools


def test_bootstrap_marks_unknown_integration(docs_registry):
    registry, git = docs_registry
    text = bootstrap_doc_qa(
        registry,
        query="do we support bytespeed integration?",
        allowed=["search_repo_docs", "read_repo_doc"],
        session=None,
        git=git,
    )
    assert "Answer **No**" in text
    assert any(item.get("tool") == "search_repo_docs" for item in registry.tool_trace)
