"""Tests for workflow gates and plan/create-pr commands."""

from __future__ import annotations

from backend.models.config import AlfredConfig, GitConfig
from backend.models.session import ConversationSession
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
    cfg.git = GitConfig(enabled=True, token="tok", main_repo="Org/cipher", write_enabled=True, **git_kw)
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
        raw_text="alfred pr on Org/cipher: add logging when fp_id is missing with unit test",
        cleaned_intent="alfred pr on Org/cipher: add logging when fp_id is missing with unit test",
    )
    result = gate_create_pr(task, _config(), session=None, slack_context=None)
    assert result.ready
    assert result.enriched_intent
    assert "Org/cipher" in result.enriched_intent


def test_gate_create_pr_multi_turn_session():
    session = ConversationSession(
        key="slack:C1:1",
        source="slack",
        scope_id="C1",
        thread_id="1",
        metadata={"workflow_create_pr": {"awaiting": ["goal"], "repo": "Org/cipher"}},
        turns=[],
    )
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        thread_ts="1",
        raw_text="add fp_id null guard with unit test",
        cleaned_intent="add fp_id null guard with unit test",
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
    assert "cipher" in build_cli_create_pr_intent("add tests", repo="Org/cipher", interactive=False, config=cfg)
    assert build_cli_plan_intent("fix bug", repo=None, interactive=False, config=cfg).startswith("alfred plan")


def test_plan_and_create_pr_skills_load(tmp_path):
    store = PlaybookStore(tmp_path)
    names = {p.name for p in store.list_playbooks()}
    assert "plan_task" in names
    assert "create_pr" in names
