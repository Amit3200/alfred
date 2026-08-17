"""Tests for Phase 1 git write guardrails and tools."""

from __future__ import annotations

import os
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
from backend.tools.git.write import register_git_write_tools
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
    validate_readonly_script_content(
        "import subprocess\nout = subprocess.run(['python3', '-c', 'print(1)'], capture_output=True, text=True)\nprint(out.stdout)"
    )
    with pytest.raises(ValueError, match="write mode"):
        validate_readonly_script_content("open('out.txt', 'w').write('x')")
    with pytest.raises(ValueError, match="shell=True"):
        validate_readonly_script_content("subprocess.run('ls', shell=True)")


def test_prepare_write_branch_resets_dirty_workspace(tmp_path: Path):
    import subprocess

    from backend.integrations.git.mirror import WorkspaceMirrorManager
    from backend.integrations.git.write_ops import prepare_write_branch

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }

    bare = tmp_path / "remote.git"
    repo = tmp_path / "FlexyPe__cipher"
    bare.mkdir()
    subprocess.run(["git", "init", "--bare", "-b", "dev"], cwd=bare, check=True, capture_output=True, env=env)
    subprocess.run(["git", "clone", str(bare), str(repo)], check=True, capture_output=True, env=env)
    subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True, capture_output=True, env=env)
    (repo / "apps" / "cipher" / "src").mkdir(parents=True)
    tracked = repo / "apps" / "cipher" / "src" / "main.ts"
    tracked.write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(["git", "push", "-u", "origin", "dev"], cwd=repo, check=True, capture_output=True, env=env)

    tracked.write_text("dirty local edit\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("leftover\n", encoding="utf-8")
    subprocess.run(["git", "checkout", "-b", "alfred/pr/old-attempt"], cwd=repo, check=True, capture_output=True, env=env)

    git = GitConfig(enabled=True, token="x", write_enabled=True, mirror_shallow_depth=50)
    mirror = MagicMock(spec=WorkspaceMirrorManager)
    mirror.git = git
    mirror.ensure_repo.return_value = MagicMock(path=repo)
    mirror._update_repo_ref = MagicMock()

    result = prepare_write_branch(
        mirror,
        "ui:chat:1",
        "FlexyPe/cipher",
        branch_name="alfred/pr/new-change",
        base_branch="dev",
    )

    assert result["branch"] == "alfred/pr/new-change"
    assert result["base_branch"] == "dev"
    assert tracked.read_text(encoding="utf-8") == "original\n"
    assert not (repo / "untracked.txt").exists()
    current_branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout.strip()
    assert current_branch == "alfred/pr/new-change"


def test_resolve_base_branch_falls_back_from_missing_main(tmp_path: Path):
    import subprocess

    from backend.integrations.git.write_ops import _detect_default_base_branch, _resolve_base_branch

    repo = tmp_path / "FlexyPe__cipher"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "dev"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=repo, check=True, capture_output=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/dev", head],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/dev"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    git = GitConfig(enabled=True, token="x", write_enabled=True)
    assert _detect_default_base_branch(repo, git) == "dev"
    assert _resolve_base_branch(repo, git, "main") == "dev"
    assert _resolve_base_branch(repo, git, None) == "dev"

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
    from backend.tools.git.write import ALFRED_PR_LABEL_PLAN, alfred_pr_labels_for_registry, register_git_write_tools

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
    with patch("backend.tools.git.write.GitApiClient") as mock_client_cls, patch(
        "backend.tools.git.write.WorkspaceMirrorManager"
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
