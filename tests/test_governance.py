"""Tests for governance policies, confirmation UX, registry wiring, and audit log."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.ai.base import ToolSchema
from backend.governance.audit import get_audit_store
from backend.governance.confirmation import (
    approval_metadata_patch,
    is_confirmation_only,
    is_confirmation_phrase,
    session_has_write_approval,
)
from backend.governance.context import GovernanceContext
from backend.models.config import AlfredConfig, GovernanceConfig
from backend.models.session import ConversationSession
from backend.models.task import Task
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult


def _task(**overrides: object) -> Task:
    base = {
        "source": "slack",
        "user_id": "U123",
        "channel_id": "C456",
        "thread_ts": "111.222",
        "raw_text": "fix bug",
        "cleaned_intent": "fix bug",
    }
    base.update(overrides)
    return Task(**base)  # type: ignore[arg-type]


def _config(**gov_overrides: object) -> AlfredConfig:
    gov = GovernanceConfig(**gov_overrides)  # type: ignore[arg-type]
    return AlfredConfig(governance=gov)


def test_confirmation_phrase_detection():
    config = _config()
    gov = config.governance
    assert is_confirmation_phrase("yes, proceed", gov)
    assert is_confirmation_phrase("@alfred yes proceed", gov)
    assert is_confirmation_only("yes, proceed", gov)
    assert not is_confirmation_phrase("fix the null pointer", gov)


def test_policy_blocks_channel(tmp_path: Path):
    config = _config(write_blocked_channels=["C456"])
    task = _task()
    ctx = GovernanceContext(config, task, data_dir=tmp_path)
    blocked = ctx.check_before_run("write_file", {"path": "src/a.py", "repo": "org/r"})
    assert blocked is not None
    assert "blocked" in blocked.data["message"].lower()


def test_policy_blocks_unauthorized_user(tmp_path: Path):
    config = _config(write_allowed_users=["U999"])
    task = _task(user_id="U123")
    ctx = GovernanceContext(config, task, data_dir=tmp_path)
    blocked = ctx.check_before_run("git_commit", {"repo": "org/r", "message": "fix"})
    assert blocked is not None
    assert "not authorized" in blocked.data["message"].lower()


def test_staging_write_skips_confirmation(tmp_path: Path):
    config = _config()
    task = _task()
    ctx = GovernanceContext(config, task, data_dir=tmp_path)
    assert ctx.check_before_run("write_file", {"path": "src/a.py", "repo": "org/r"}) is None
    assert ctx.check_before_run("git_commit", {"repo": "org/r", "message": "fix"}) is None


def test_publish_tools_require_confirmation(tmp_path: Path):
    config = _config()
    task = _task()
    ctx = GovernanceContext(config, task, data_dir=tmp_path)
    blocked = ctx.check_before_run(
        "create_pull_request",
        {"repo": "org/r", "title": "Fix", "head": "alfred/x", "base": "main"},
    )
    assert blocked is not None
    assert "requires explicit approval" in blocked.data["message"]


def test_session_approval_allows_publish(tmp_path: Path):
    config = _config()
    task = _task()
    session = ConversationSession(
        key="slack:C456:111.222",
        source="slack",
        scope_id="C456",
        thread_id="111.222",
        metadata=approval_metadata_patch(user_id="U123", ttl_minutes=30),
    )
    assert session_has_write_approval(session, config.governance)
    ctx = GovernanceContext(config, task, session=session, data_dir=tmp_path)
    assert ctx.check_before_run(
        "git_push_branch",
        {"repo": "org/r", "branch": "alfred/fix"},
    ) is None


def test_cli_skips_confirmation_by_default(tmp_path: Path):
    config = _config()
    task = _task(source="cli", channel_id="", thread_ts=None)
    ctx = GovernanceContext(config, task, data_dir=tmp_path)
    assert ctx.check_before_run(
        "git_push_branch",
        {"repo": "org/r", "branch": "alfred/fix"},
    ) is None


def test_registry_governance_blocks_and_audits(tmp_path: Path):
    registry = ToolRegistry()
    registry.register(
        ToolSchema(
            name="git_push_branch",
            description="push",
            parameters={"type": "object", "properties": {}},
        ),
        lambda _args: ToolResult(kind="pushed", data={"ok": True}),
    )
    config = _config()
    task = _task()
    registry.governance = GovernanceContext(config, task, data_dir=tmp_path)

    result = registry.run("git_push_branch", {"repo": "org/r", "branch": "alfred/x"}, allowed=["git_push_branch"])
    assert result.kind == "error"

    rows = get_audit_store(tmp_path).list_recent(limit=5, blocked_only=True)
    assert rows
    assert rows[0]["tool_name"] == "git_push_branch"
    assert rows[0]["blocked"] is True


def test_registry_audits_successful_staging_write(tmp_path: Path):
    registry = ToolRegistry()
    registry.register(
        ToolSchema(
            name="write_file",
            description="write",
            parameters={"type": "object", "properties": {}},
        ),
        lambda _args: ToolResult(kind="file_written", data={"path": "src/a.py"}),
    )
    config = _config()
    task = _task()
    registry.governance = GovernanceContext(config, task, data_dir=tmp_path)

    result = registry.run(
        "write_file",
        {"repo": "org/r", "path": "src/a.py", "content": "x"},
        allowed=["write_file"],
    )
    assert result.kind == "file_written"

    rows = get_audit_store(tmp_path).list_recent(limit=5, tool_name="write_file")
    assert len(rows) == 1
    assert rows[0]["success"] is True
    assert rows[0]["blocked"] is False
