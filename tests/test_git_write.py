"""Tests for Phase 1 git write guardrails and tools."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.integrations.git.guardrails import (
    assert_write_path_allowed,
    validate_branch_name,
    validate_readonly_script_content,
)
from backend.models.config import GitConfig
from backend.tools.git_write import register_git_write_tools
from backend.tools.registry import ToolRegistry


def test_validate_branch_rejects_protected():
    git = GitConfig(enabled=True, token="x", write_enabled=True)
    with pytest.raises(ValueError, match="protected"):
        validate_branch_name(git, "main")
    assert validate_branch_name(git, "alfred/fix-null-fp") == "alfred/fix-null-fp"


def test_write_path_blocks_infra():
    git = GitConfig(enabled=True, token="x", write_enabled=True)
    with pytest.raises(ValueError, match="blocked"):
        assert_write_path_allowed(git, ".github/workflows/ci.yml")
    rel = assert_write_path_allowed(git, "src/handler.py")
    assert rel == "src/handler.py"


def test_debug_script_path_and_content():
    git = GitConfig(enabled=True, token="x", write_enabled=True)
    rel = assert_write_path_allowed(git, "scripts/alfred_debug/inspect.py", debug_script=True)
    assert rel.endswith("inspect.py")
    validate_readonly_script_content("print(open('foo').read())")
    with pytest.raises(ValueError, match="write mode"):
        validate_readonly_script_content("open('out.txt', 'w').write('x')")


def test_write_tools_not_registered_when_disabled(tmp_path: Path):
    registry = ToolRegistry()
    registry.workspace_id = "slack:C1:123"
    config = MagicMock()
    config.git = GitConfig(enabled=True, token="tok", write_enabled=False)
    register_git_write_tools(registry, config=config, data_dir=tmp_path)
    assert "git_prepare_branch" not in registry._tools


def test_write_tools_registered_when_enabled(tmp_path: Path):
    registry = ToolRegistry()
    registry.workspace_id = "slack:C1:123"
    config = MagicMock()
    config.git = GitConfig(enabled=True, token="tok", write_enabled=True)
    register_git_write_tools(registry, config=config, data_dir=tmp_path)
    assert "create_pull_request" in registry._tools
    assert "run_debug_script" in registry._tools


def test_create_pr_skill_bundled(tmp_path: Path):
    from backend.routing.playbooks import PlaybookStore

    store = PlaybookStore(tmp_path)
    skill = store.get_by_name("create_pr")
    assert skill is not None
    assert skill.mode == "workflow"
    assert "git_prepare_branch" in skill.allowed_tools
    assert "create_pull_request" in skill.allowed_tools


def test_create_pull_request_github_api():
    from backend.integrations.git.api import GitApiClient

    git = GitConfig(enabled=True, provider="github", token="ghp_test", write_enabled=True)
    client = GitApiClient(git)
    with patch.object(client._impl, "_post") as mock_post:
        mock_post.return_value = {
            "number": 99,
            "title": "fix: test",
            "state": "open",
            "html_url": "https://github.com/org/cipher/pull/99",
            "head": {"ref": "alfred/fix"},
            "base": {"ref": "main"},
            "draft": True,
        }
        detail = client.create_pull_request(
            "org/cipher",
            title="fix: test",
            head="alfred/fix",
            base="main",
            body="plan",
            draft=True,
        )
    assert detail["number"] == 99
    assert detail["url"].endswith("/pull/99")
    mock_post.assert_called_once()
