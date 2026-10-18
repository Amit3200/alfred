"""Tests for repository profiles and knowledge-base flags."""

from __future__ import annotations

from backend.context.repo_profiles import (
    effective_doc_index,
    effective_graphify,
    list_configured_repos,
    should_doc_index_on_sync,
    should_graphify_on_sync,
)
from backend.models.config import AlfredConfig, GitConfig, GitRepoProfile, RepoKnowledgeConfig


def _config(**git_overrides) -> AlfredConfig:
    git = GitConfig(
        enabled=True,
        token="test",
        default_org="Acme",
        repos=["Acme/app"],
        main_repo="Acme/app",
        graphify_enabled=True,
        **git_overrides,
    )
    return AlfredConfig(git=git, repo_knowledge=RepoKnowledgeConfig(enabled=True, index_on_sync=True))


def test_list_configured_repos_merges_profiles():
    cfg = _config(
        repo_profiles=[
            GitRepoProfile(repo="Acme/docs", role="docs"),
            GitRepoProfile(repo="Acme/dailyscripts", role="scripts"),
        ],
    )
    repos = list_configured_repos(cfg.git)
    assert repos[0] == "Acme/app"
    assert "Acme/docs" in repos
    assert "Acme/dailyscripts" in repos


def test_docs_profile_defaults():
    profile = GitRepoProfile(repo="Acme/docs", role="docs")
    assert effective_doc_index(profile) is True
    assert effective_graphify(profile, graphify_enabled=True) is True
    assert effective_graphify(profile, graphify_enabled=False) is False


def test_scripts_profile_skips_knowledge_build():
    cfg = _config(
        repo_profiles=[GitRepoProfile(repo="Acme/dailyscripts", role="scripts")],
    )
    assert should_doc_index_on_sync(cfg, "Acme/dailyscripts") is False
    assert should_graphify_on_sync(cfg, "Acme/dailyscripts") is False


def test_docs_profile_enables_index_and_graph_on_sync():
    cfg = _config(
        repo_profiles=[GitRepoProfile(repo="Acme/docs", role="docs")],
    )
    assert should_doc_index_on_sync(cfg, "Acme/docs") is True
    assert should_graphify_on_sync(cfg, "Acme/docs") is True


def test_doc_paths_for_docs_role():
    cfg = _config(
        repo_profiles=[GitRepoProfile(repo="Acme/docs", role="docs")],
    )
    from backend.context.repo_profiles import doc_paths_for_repo

    assert doc_paths_for_repo(cfg, "Acme/docs") == ["."]


def test_main_repo_graphify_without_profile():
    cfg = _config()
    assert should_graphify_on_sync(cfg, "Acme/app") is True
    assert should_graphify_on_sync(cfg, "Acme/other") is False
