"""Tests for local git mirror tools."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from backend.models.config import AlfredConfig, default_config
from backend.tools.builder import build_git_tool_registry
from backend.tools.registry import ToolRegistry
from tests.paths import SAMPLE_REPO


def _registry_with_fixture(tmp_path: Path) -> ToolRegistry:
    config = default_config()
    config.git.enabled = True
    config.git.token = "test"
    config.git.repos = ["acme/backend"]

    fixture = SAMPLE_REPO
    shared = tmp_path / "repos" / "shared" / "acme__backend"
    shared.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(fixture, shared)

    registry = build_git_tool_registry(
        config,
        workspace_id="ui:test:test",
        data_dir=tmp_path,
    )
    return registry


def test_grep_repo_finds_duplicate_order(tmp_path):
    registry = _registry_with_fixture(tmp_path)
    result = registry.run(
        "grep_repo",
        {"repo": "acme/backend", "pattern": "duplicate order"},
        allowed=["grep_repo"],
    )
    assert result.kind == "code_grep"
    matches = result.data["matches"]
    assert matches
    assert any("order_handler.py" in m["path"] for m in matches)


def test_read_file_returns_snippet(tmp_path):
    registry = _registry_with_fixture(tmp_path)
    result = registry.run(
        "read_file",
        {"repo": "acme/backend", "path": "order_handler.py", "start_line": 1, "end_line": 5},
        allowed=["read_file"],
    )
    assert result.kind == "file_content"
    assert "is_duplicate_order" in result.data["content"]


def _init_git_repo(path: Path) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=path,
        check=True,
        capture_output=True,
        env=env,
    )


def test_git_show_returns_commit_output(tmp_path):
    registry = _registry_with_fixture(tmp_path)
    shared = tmp_path / "repos" / "shared" / "acme__backend"
    _init_git_repo(shared)
    result = registry.run(
        "git_show",
        {"repo": "acme/backend", "ref": "HEAD"},
        allowed=["git_show"],
    )
    assert result.kind == "git_show"
    assert result.data["output"]
