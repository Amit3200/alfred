"""Tests for plan→PR handoff helpers and workflow integration."""

from __future__ import annotations

from pathlib import Path

from backend.models.config import AlfredConfig, GitConfig
from backend.models.session import ConversationSession
from backend.models.task import Task
from backend.orchestrator.planning import (
    adopt_session_plan_for_task,
    plan_exists_for_task,
    resolve_plan_for_task,
)
from backend.orchestrator.workflow_gates import gate_create_pr


def _config() -> AlfredConfig:
    cfg = AlfredConfig()
    cfg.git = GitConfig(enabled=True, token="tok", main_repo="Org/cipher", write_enabled=True)
    return cfg


def test_adopt_session_plan_for_task(tmp_path: Path):
    plans = tmp_path / "plans"
    plans.mkdir()
    source = plans / "plan_old.md"
    source.write_text("# Task Plan\n- [ ] Add logging for missing fp_id\n", encoding="utf-8")
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
    assert "fp_id" in resolve_plan_for_task(task.id, session=session, data_dir=tmp_path) or ""


def test_gate_create_pr_inherits_plan_session(tmp_path: Path):
    plans = tmp_path / "plans"
    plans.mkdir()
    plan_path = plans / "plan_plan123.md"
    plan_path.write_text(
        "# Task Plan\n- [ ] Add null guard when fp_id missing in checkout handler with unit test\n",
        encoding="utf-8",
    )
    session = ConversationSession(
        key="slack:C1:1",
        source="slack",
        scope_id="C1",
        thread_id="1",
        metadata={
            "plan_file": str(plan_path),
            "workflow_plan": {
                "goal": "Add null guard when fp_id missing in checkout handler with unit test",
                "repo": "Org/cipher",
                "ready": True,
            },
        },
    )
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        thread_ts="1",
        raw_text="alfred pr",
        cleaned_intent="alfred pr",
    )
    result = gate_create_pr(task, _config(), session=session, slack_context=None)
    assert result.ready
    assert result.enriched_intent
    assert "approved task plan" in (result.enriched_intent or "").lower()
    assert result.metadata_patch.get("inherit_plan_file") == str(plan_path)


def test_gate_create_pr_plan_handoff_phrase():
    session = ConversationSession(
        key="slack:C1:1",
        source="slack",
        scope_id="C1",
        thread_id="1",
        metadata={
            "workflow_plan": {
                "goal": "Instrument checkout duplicate order detection with metrics",
                "repo": "Org/cipher",
            }
        },
    )
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        thread_ts="1",
        raw_text="implement the plan",
        cleaned_intent="implement the plan on Org/cipher",
    )
    result = gate_create_pr(task, _config(), session=session, slack_context=None)
    assert result.ready
    assert "Org/cipher" in (result.enriched_intent or "")
