"""Tests for doc index path rules and MDX support."""

from __future__ import annotations

from backend.context.doc_index import build_doc_index, pick_best_doc_hit, search_repo_docs
from backend.context.repo_profiles import doc_paths_for_repo, doc_search_repo_slugs
from backend.models.config import AlfredConfig, GitConfig, GitRepoProfile, RepoKnowledgeConfig


def test_doc_paths_for_docs_role_indexes_whole_mirror():
    cfg = AlfredConfig(
        git=GitConfig(
            repo_profiles=[GitRepoProfile(repo="acme/docs", role="docs")],
        ),
    )
    assert doc_paths_for_repo(cfg, "acme/docs") == ["."]


def test_doc_paths_for_code_role_uses_defaults():
    cfg = AlfredConfig(
        git=GitConfig(
            repo_profiles=[GitRepoProfile(repo="acme/app", role="code")],
        ),
    )
    assert doc_paths_for_repo(cfg, "acme/app") == ["docs", "runbooks", "README.md"]


def test_build_doc_index_includes_mdx_under_integrations(tmp_path):
    mirror = tmp_path / "repos" / "shared" / "acme__docs"
    mirror.mkdir(parents=True)
    (mirror / "integrations" / "analytics").mkdir(parents=True)
    (mirror / "integrations" / "analytics" / "google-ads.mdx").write_text(
        "# Google Ads\n\nConfigure Google Ads integration with conversion tracking.\n",
        encoding="utf-8",
    )

    git = GitConfig(
        enabled=True,
        default_org="acme",
        main_repo="acme/docs",
        repo_profiles=[GitRepoProfile(repo="acme/docs", role="docs", doc_index=True)],
    )
    cfg = AlfredConfig(git=git, repo_knowledge=RepoKnowledgeConfig(enabled=True))

    manifest = build_doc_index(tmp_path, git, repo="acme/docs", alfred_config=cfg)
    paths = {chunk["path"] for chunk in manifest["chunks"]}
    assert "integrations/analytics/google-ads.mdx" in paths

    hits = search_repo_docs(tmp_path, "acme/docs", "Google Ads conversion tracking", limit=5)
    assert hits
    assert any("google-ads" in hit["path"] for hit in hits)


def test_doc_search_skips_code_repo_when_doc_index_disabled(tmp_path, monkeypatch):
    git = GitConfig(
        enabled=True,
        default_org="FlexyPe",
        main_repo="FlexyPe/cipher",
        repos=["FlexyPe/cipher", "FlexyPe/docs"],
        repo_profiles=[
            GitRepoProfile(repo="FlexyPe/cipher", role="code", doc_index=False),
            GitRepoProfile(repo="FlexyPe/docs", role="docs", doc_index=True),
        ],
    )
    cfg = AlfredConfig(git=git, repo_knowledge=RepoKnowledgeConfig(enabled=True))

    for slug in ("FlexyPe/cipher", "FlexyPe/docs"):
        mirror = tmp_path / "repos" / "shared" / slug.replace("/", "__")
        mirror.mkdir(parents=True)
        (mirror / "readme.md").write_text("# Readme\n", encoding="utf-8")
        build_doc_index(tmp_path, git, repo=slug, alfred_config=cfg)

    slugs = doc_search_repo_slugs(cfg, tmp_path)
    assert slugs == ["FlexyPe/docs"]


def test_pick_best_doc_hit_prefers_handbook_over_playbook():
    hits = [
        {"path": "playbooks/investigate_bug.md", "score": 8.5, "repo": "FlexyPe/cipher"},
        {"path": "handbook/upsell.mdx", "score": 6.0, "repo": "FlexyPe/docs"},
    ]
    best = pick_best_doc_hit(hits, "what is upselling and how to configure it")
    assert best is not None
    assert best["path"] == "handbook/upsell.mdx"


def test_code_repo_index_excludes_playbooks(tmp_path, monkeypatch):
    empty_skills = tmp_path / "empty_skills"
    empty_skills.mkdir()
    monkeypatch.setattr("backend.context.doc_index.bundled_skills_dir", lambda: empty_skills)
    (empty_skills / "investigate_bug.md").write_text("# Bug\n", encoding="utf-8")

    mirror = tmp_path / "repos" / "shared" / "FlexyPe__cipher"
    (mirror / "docs").mkdir(parents=True)
    (mirror / "docs" / "api.md").write_text("# API\n", encoding="utf-8")

    git = GitConfig(
        enabled=True,
        default_org="FlexyPe",
        main_repo="FlexyPe/cipher",
        repo_profiles=[GitRepoProfile(repo="FlexyPe/cipher", role="code", doc_index=True)],
    )
    cfg = AlfredConfig(git=git, repo_knowledge=RepoKnowledgeConfig(enabled=True))
    manifest = build_doc_index(tmp_path, git, repo="FlexyPe/cipher", alfred_config=cfg)
    paths = {chunk["path"] for chunk in manifest["chunks"]}
    assert "docs/api.md" in paths
    assert not any(path.startswith("playbooks/") for path in paths)
