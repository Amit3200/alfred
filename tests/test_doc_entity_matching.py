"""Entity-aware doc search — avoid wrong integration answers."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.context.doc_index import (
    build_doc_index,
    doc_hit_matches_query,
    pick_best_doc_hit,
    search_repo_docs,
    significant_query_tokens,
)
from backend.models.config import AlfredConfig, GitConfig, GitRepoProfile, RepoKnowledgeConfig


@pytest.fixture
def docs_index(tmp_path: Path, monkeypatch):
    empty_skills = tmp_path / "empty_skills"
    empty_skills.mkdir()
    monkeypatch.setattr("backend.routing.playbooks.bundled_skills_dir", lambda: empty_skills)
    monkeypatch.setattr("backend.context.doc_index._collect_playbook_docs", lambda _data_dir: [])

    mirror = tmp_path / "repos" / "shared" / "FlexyPe__docs"
    (mirror / "platforms").mkdir(parents=True)
    (mirror / "integrations" / "analytics").mkdir(parents=True)
    (mirror / "platforms" / "shopify.mdx").write_text(
        "# Shopify\n\nIntegrate FlexyPe checkout with your Shopify store.\n",
        encoding="utf-8",
    )
    (mirror / "integrations" / "analytics" / "google-ads.mdx").write_text(
        "# Google Ads\n\nConnect Google Ads via Analytics settings.\n",
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
    return tmp_path, git


def test_significant_tokens_strip_integration_noise():
    tokens = significant_query_tokens("Do we have bytespeed integration and how can we do it?")
    assert "bytespeed" in tokens
    assert "integration" not in tokens


def test_bytespeed_query_does_not_match_shopify(docs_index):
    data_dir, _git = docs_index
    query = "Do we have bytespeed integration and how can we do it?"
    hits = search_repo_docs(data_dir, "FlexyPe/docs", query, limit=5)
    assert hits
    assert pick_best_doc_hit(hits, query) is None
    assert not any(doc_hit_matches_query(hit, query) for hit in hits)


def test_google_ads_query_matches_correct_doc(docs_index):
    data_dir, _git = docs_index
    query = "How google ads can be configured and integrated?"
    hits = search_repo_docs(data_dir, "FlexyPe/docs", query, limit=5)
    best = pick_best_doc_hit(hits, query)
    assert best is not None
    assert "google-ads" in str(best.get("path") or "")


def test_execute_repo_doc_qa_direct_says_no_for_unknown_integration(tmp_path: Path, monkeypatch):
    empty_skills = tmp_path / "empty_skills"
    empty_skills.mkdir()
    monkeypatch.setattr("backend.routing.playbooks.bundled_skills_dir", lambda: empty_skills)
    monkeypatch.setattr("backend.context.doc_index._collect_playbook_docs", lambda _data_dir: [])

    from shutil import copy

    copy(
        Path(__file__).resolve().parents[1] / "skills" / "repo_knowledge.md",
        empty_skills / "repo_knowledge.md",
    )

    mirror = tmp_path / "repos" / "shared" / "FlexyPe__docs"
    (mirror / "platforms").mkdir(parents=True)
    (mirror / "platforms" / "shopify.mdx").write_text(
        "# Shopify\n\nShopify integration steps.\n" * 200,
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

    from backend.models.task import Task
    from backend.orchestrator.processor import TaskProcessor
    from backend.routing.playbook_store_registry import get_playbook_store

    store = get_playbook_store(tmp_path, disabled_skills=[])
    processor = TaskProcessor(config, data_dir=tmp_path, playbook_store=store)
    skill = store.get_by_name("repo_knowledge")
    assert skill is not None

    task = Task(
        source="ui",
        user_id="u1",
        channel_id="c1",
        raw_text="Do we have bytespeed integration and how can we do it?",
        cleaned_intent="Do we have bytespeed integration and how can we do it?",
        metadata={"chat_persona_effective": "support"},
    )

    response, _patch = processor._execute_repo_doc_qa_direct(
        skill,
        task,
        None,
        task.cleaned_intent,
    )
    text = (response.text or str(response.payload.data.get("text") or "")).lower()
    meta = response.payload.data.get("reply_meta") or {}
    assert meta.get("relevancy") == "not_found"
    assert "no" in text
    assert "bytespeed" in text
    assert "shopify" not in text
