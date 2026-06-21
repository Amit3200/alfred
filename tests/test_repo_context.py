"""Tests for main-repo context generation."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from backend.context.generator import (
    context_status,
    generate_repo_context,
    load_repo_context_for_prompt,
    resolve_main_repo,
    shared_mirror_path,
)
from backend.git.api import resolve_repo_slug
from backend.git.mirror import WorkspaceMirrorManager
from backend.models.config import GitConfig


def _git_config(**overrides) -> GitConfig:
    base = dict(
        enabled=True,
        provider="github",
        token="test",
        default_org="acme",
        repos=["acme/backend"],
        main_repo="backend",
    )
    base.update(overrides)
    return GitConfig(**base)


def test_resolve_main_repo_expands_short_name():
    git = _git_config()
    assert resolve_main_repo(git) == "acme/backend"


def test_resolve_repo_slug_uses_main_repo_short_name():
    git = _git_config()
    assert resolve_repo_slug("backend", git) == "acme/backend"


def test_sync_targets_puts_main_repo_first(tmp_path):
    git = _git_config(repos=["acme/other", "acme/backend"])
    manager = WorkspaceMirrorManager(git, tmp_path)
    targets = manager._sync_targets(None)
    assert targets[0] == "acme/backend"
    assert set(targets) == {"acme/backend", "acme/other"}


def test_generate_repo_context_writes_markdown(tmp_path):
    fixture = Path(__file__).resolve().parent / "fixtures" / "sample-repo"
    git = _git_config()
    slug = "acme/backend"
    mirror = shared_mirror_path(tmp_path, slug)
    shutil.copytree(fixture, mirror)

    manifest = generate_repo_context(tmp_path, git, repo=slug)

    assert manifest["repo"] == slug
    ctx_dir = tmp_path / "context" / "acme__backend"
    assert (ctx_dir / "overview.md").is_file()
    assert (ctx_dir / "layout.md").is_file()
    overview = (ctx_dir / "overview.md").read_text(encoding="utf-8")
    assert "acme/backend" in overview
    assert "Sample repo" in overview


def test_load_repo_context_for_prompt(tmp_path):
    fixture = Path(__file__).resolve().parent / "fixtures" / "sample-repo"
    git = _git_config()
    slug = "acme/backend"
    shutil.copytree(fixture, shared_mirror_path(tmp_path, slug))
    generate_repo_context(tmp_path, git, repo=slug)

    prompt = load_repo_context_for_prompt(tmp_path, git)
    assert "## Main repository context" in prompt
    assert "acme/backend" in prompt
    assert "Repository layout" in prompt


def test_generate_requires_shared_mirror(tmp_path):
    git = _git_config()
    with pytest.raises(FileNotFoundError):
        generate_repo_context(tmp_path, git, repo="acme/backend")


def test_context_status_unconfigured(tmp_path):
    git = _git_config(main_repo="")
    status = context_status(tmp_path, git)
    assert status["configured"] is False


def test_main_repo_allowed_without_repos_list(tmp_path):
    git = GitConfig(
        enabled=True,
        token="test",
        default_org="acme",
        repos=["acme/other"],
        main_repo="acme/backend",
    )
    manager = WorkspaceMirrorManager(git, tmp_path)
    manager._assert_repo_allowed("acme/backend")
