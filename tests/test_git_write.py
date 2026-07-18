"""Tests for Phase 1 git write guardrails and tools."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.integrations.git.guardrails import (
    assert_write_path_allowed,
    format_alfred_pr_branch_name,
    resolve_alfred_pr_branch_name,
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
    assert validate_branch_name(git, "alfred/pr/fix-null-fp") == "alfred/pr/fix-null-fp"


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


def test_resolve_alfred_pr_branch_name():
    assert format_alfred_pr_branch_name("Instrument Checkout Handler") == "alfred/pr/instrument-checkout-handler"
    assert resolve_alfred_pr_branch_name(branch_context="fix null fp") == "alfred/pr/fix-null-fp"
    assert resolve_alfred_pr_branch_name(branch_name="alfred/pr/custom-branch") == "alfred/pr/custom-branch"
    assert resolve_alfred_pr_branch_name(branch_name="alfred/legacy-name") == "alfred/pr/legacy-name"


def test_create_pull_request_github_api():
    from backend.integrations.git.api import GitApiClient

    git = GitConfig(enabled=True, provider="github", token="ghp_test", write_enabled=True)
    client = GitApiClient(git)
    with patch.object(client._impl, "_post") as mock_post:
        mock_post.return_value = {
            "number": 99,
            "title": "fix: test",
            "state": "open",
            "html_url": "https://github.com/org/backend/pull/99",
            "head": {"ref": "alfred/pr/fix"},
            "base": {"ref": "main"},
            "draft": True,
        }
        detail = client.create_pull_request(
            "org/backend",
            title="fix: test",
            head="alfred/pr/fix",
            base="main",
            body="plan",
            draft=True,
            labels=["alfred-generated", "alfred-plan"],
        )
    assert detail["number"] == 99
    assert detail["url"].endswith("/pull/99")
    assert detail["labels"] == ["alfred-generated", "alfred-plan"]
    assert mock_post.call_count == 2
    label_call = mock_post.call_args_list[1]
    assert "issues/99/labels" in label_call.args[0]
    assert label_call.kwargs["json"]["labels"] == ["alfred-generated", "alfred-plan"]


def test_create_pull_request_applies_labels_from_governance(tmp_path: Path):
    from backend.governance.context import GovernanceContext
    from backend.models.config import AlfredConfig, GovernanceConfig
    from backend.models.task import Task
    from backend.tools.git_write import ALFRED_PR_LABEL_PLAN, alfred_pr_labels_for_registry, register_git_write_tools

    plans = tmp_path / "plans"
    plans.mkdir()
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        thread_ts="1",
        raw_text="alfred pr",
        cleaned_intent="fix bug",
    )
    (plans / f"plan_{task.id}.md").write_text("# Task Plan\n", encoding="utf-8")

    registry = ToolRegistry()
    registry.workspace_id = "slack:C1:1"
    registry.governance = GovernanceContext(
        AlfredConfig(governance=GovernanceConfig()),
        task,
        data_dir=tmp_path,
    )
    assert alfred_pr_labels_for_registry(registry, tmp_path) == ["alfred-generated", ALFRED_PR_LABEL_PLAN]

    config = AlfredConfig(
        git=GitConfig(
            enabled=True,
            provider="github",
            token="ghp_test",
            write_enabled=True,
            main_repo="org/backend",
        ),
        governance=GovernanceConfig(enabled=False),
    )
    registry.governance = GovernanceContext(config, task, data_dir=tmp_path)
    with patch("backend.tools.git_write.GitApiClient") as mock_client_cls, patch(
        "backend.tools.git_write.WorkspaceMirrorManager"
    ):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.create_pull_request.return_value = {
            "number": 1,
            "url": "https://github.com/org/backend/pull/1",
            "labels": ["alfred-generated", "alfred-plan"],
        }
        register_git_write_tools(registry, config=config, data_dir=tmp_path)
        result = registry.run(
            "create_pull_request",
            {"repo": "org/backend", "title": "Fix", "head": "alfred/fix", "base": "main"},
            allowed=["create_pull_request"],
        )

    assert result.kind == "pr_created"
    mock_client.create_pull_request.assert_called_once()
    call_kwargs = mock_client.create_pull_request.call_args.kwargs
    assert call_kwargs["head"] == "alfred/pr/fix"
    assert call_kwargs["labels"] == ["alfred-generated", "alfred-plan"]
