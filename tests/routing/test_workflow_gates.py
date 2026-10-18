"""Tests for workflow gates and plan/create-pr commands."""

from __future__ import annotations

from backend.models.config import AlfredConfig, GitConfig
from backend.models.session import ConversationSession, ConversationTurn
from backend.models.task import Task
from backend.orchestrator.workflow_gates import (
    build_cli_create_pr_intent,
    build_cli_plan_intent,
    gate_create_pr,
    gate_plan_task,
)
from backend.routing.playbooks import PlaybookStore


def _config(**git_kw) -> AlfredConfig:
    cfg = AlfredConfig()
    cfg.git = GitConfig(enabled=True, token="tok", main_repo="Org/backend", write_enabled=True, **git_kw)
    return cfg


def test_gate_create_pr_bare_asks_questions():
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        thread_ts="1",
        raw_text="alfred pr",
        cleaned_intent="alfred pr",
    )
    result = gate_create_pr(task, _config(), session=None, slack_context=None)
    assert not result.ready
    assert "implement" in result.message.lower() or "repository" in result.message.lower()


def test_gate_create_pr_with_context_ready():
    task = Task(
        source="cli",
        user_id="cli",
        raw_text="alfred pr on Org/backend: add logging when order_id is missing with unit test",
        cleaned_intent="alfred pr on Org/backend: add logging when order_id is missing with unit test",
    )
    result = gate_create_pr(task, _config(), session=None, slack_context=None)
    assert result.ready
    assert result.enriched_intent
    assert "Org/backend" in result.enriched_intent


def test_gate_create_pr_proceed_after_work_done():
    session = ConversationSession(
        key="ui:chat:1",
        source="ui",
        scope_id="chat",
        thread_id="1",
        metadata={
            "workflow_create_pr": {
                "repo": "Acme/app",
                "goal": "Integrate libs/insights-usage with libs/grade for success/failure events",
                "ready": True,
            }
        },
        turns=[
            ConversationTurn(role="user", content="Integrate grade with insights-usage and open a draft PR"),
            ConversationTurn(role="assistant", content="Branch alfred/pr/foo is committed. Reply yes, proceed."),
        ],
    )
    task = Task(
        source="ui",
        user_id="u",
        channel_id="chat1",
        raw_text="yes",
        cleaned_intent="yes",
    )
    result = gate_create_pr(
        task,
        _config(),
        session=session,
        slack_context=None,
    )
    assert result.ready
    assert "git_push_branch" in (result.enriched_intent or "") or "Push the committed branch" in (result.enriched_intent or "")


def test_gate_create_pr_does_not_use_yes_as_goal():
    session = ConversationSession(
        key="slack:C1:1",
        source="slack",
        scope_id="C1",
        thread_id="1",
        metadata={"workflow_create_pr": {"awaiting": ["goal"], "repo": "Org/backend"}},
        turns=[],
    )
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        thread_ts="1",
        raw_text="yes",
        cleaned_intent="yes",
    )
    result = gate_create_pr(task, _config(), session=session, slack_context=None)
    assert not result.ready
    assert "yes" not in (result.message.lower())


def test_gate_create_pr_multi_turn_session():
    session = ConversationSession(
        key="slack:C1:1",
        source="slack",
        scope_id="C1",
        thread_id="1",
        metadata={"workflow_create_pr": {"awaiting": ["goal"], "repo": "Org/backend"}},
        turns=[],
    )
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        thread_ts="1",
        raw_text="add order_id null guard with unit test",
        cleaned_intent="add order_id null guard with unit test",
    )
    result = gate_create_pr(task, _config(), session=session, slack_context=None)
    assert result.ready


def test_gate_plan_bare_asks():
    task = Task(
        source="ui",
        user_id="u",
        channel_id="chat1",
        raw_text="alfred plan",
        cleaned_intent="alfred plan",
        metadata={"chat_id": "chat1"},
    )
    result = gate_plan_task(task, AlfredConfig(), session=None, slack_context=None)
    assert not result.ready


def test_gate_plan_with_description_ready():
    task = Task(
        source="cli",
        user_id="cli",
        raw_text="alfred plan instrument checkout for duplicate orders",
        cleaned_intent="alfred plan instrument checkout for duplicate orders",
    )
    result = gate_plan_task(task, _config(), session=None, slack_context=None)
    assert result.ready
    assert "instrument checkout" in (result.enriched_intent or "")


def test_build_cli_intents():
    cfg = _config()
    assert "backend" in build_cli_create_pr_intent("add tests", repo="Org/backend", interactive=False, config=cfg)
    assert build_cli_plan_intent("fix bug", repo=None, interactive=False, config=cfg).startswith("alfred plan")


def test_plan_and_create_pr_skills_load(tmp_path):
    store = PlaybookStore(tmp_path)
    names = {p.name for p in store.list_playbooks()}
    assert "plan_task" in names
    assert "create_pr" in names
