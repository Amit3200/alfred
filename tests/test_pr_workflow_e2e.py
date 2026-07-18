"""End-to-end style tests for governance + publish tool workflow."""

from __future__ import annotations

from pathlib import Path

from backend.ai.base import ToolSchema
from backend.governance.confirmation import approval_metadata_patch
from backend.governance.context import GovernanceContext
from backend.models.config import AlfredConfig, GitConfig, GovernanceConfig
from backend.models.session import ConversationSession
from backend.models.task import Task
from backend.orchestrator.planning import adopt_session_plan_for_task, plan_exists_for_task
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult


def _config() -> AlfredConfig:
    return AlfredConfig(
        git=GitConfig(enabled=True, token="tok", write_enabled=True, main_repo="Org/backend"),
        governance=GovernanceConfig(enabled=True, require_confirmation=True),
    )


def test_publish_flow_requires_then_allows_after_approval(tmp_path: Path):
    registry = ToolRegistry()
    calls: list[str] = []

    def _register(name: str) -> None:
        registry.register(
            ToolSchema(name=name, description=name, parameters={"type": "object", "properties": {}}),
            lambda _args, tool=name: (
                calls.append(tool) or ToolResult(kind=f"{tool}_ok", data={"ok": True})
            ),
        )

    for tool in ("write_file", "git_commit", "git_push_branch", "create_pull_request"):
        _register(tool)

    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        thread_ts="1",
        raw_text="alfred pr",
        cleaned_intent="alfred pr on Org/backend: add order_id guard",
    )
    session = ConversationSession(
        key="slack:C1:1",
        source="slack",
        scope_id="C1",
        thread_id="1",
    )
    registry.governance = GovernanceContext(_config(), task, session=session, data_dir=tmp_path)

    staging = registry.run("write_file", {"repo": "Org/backend", "path": "src/a.py"}, allowed=["write_file"])
    assert staging.kind == "write_file_ok"
    commit = registry.run("git_commit", {"repo": "Org/backend", "message": "fix"}, allowed=["git_commit"])
    assert commit.kind == "git_commit_ok"

    blocked = registry.run(
        "git_push_branch",
        {"repo": "Org/backend", "branch": "alfred/fix"},
        allowed=["git_push_branch"],
    )
    assert blocked.kind == "error"

    session.metadata = approval_metadata_patch(user_id="U1", ttl_minutes=30)
    registry.governance = GovernanceContext(_config(), task, session=session, data_dir=tmp_path)
    push = registry.run(
        "git_push_branch",
        {"repo": "Org/backend", "branch": "alfred/fix"},
        allowed=["git_push_branch"],
    )
    assert push.kind == "git_push_branch_ok"
    pr = registry.run(
        "create_pull_request",
        {"repo": "Org/backend", "title": "Fix", "head": "alfred/fix", "base": "main"},
        allowed=["create_pull_request"],
    )
    assert pr.kind == "create_pull_request_ok"
    assert calls == ["write_file", "git_commit", "git_push_branch", "create_pull_request"]


def test_plan_adoption_skips_duplicate_plan_file(tmp_path: Path):
    plans = tmp_path / "plans"
    plans.mkdir()
    source = plans / "plan_old.md"
    source.write_text("# Task Plan\n- [ ] Step one\n", encoding="utf-8")
    session = ConversationSession(
        key="slack:C1:1",
        source="slack",
        scope_id="C1",
        thread_id="1",
        metadata={"plan_file": str(source)},
    )
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        thread_ts="1",
        raw_text="alfred pr",
        cleaned_intent="alfred pr",
    )
    adopted = adopt_session_plan_for_task(task, session, tmp_path)
    assert adopted
    assert plan_exists_for_task(task.id, tmp_path)
