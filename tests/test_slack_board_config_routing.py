"""Routing must not send Slack board config questions to repo doc Q&A."""

from __future__ import annotations

from backend.models.config import AlfredConfig, SlackConfig
from backend.models.task import Task
from backend.routing.entity_extractor import extract_entities
from backend.routing.slack_board_admin import try_slack_board_admin_command
from backend.routing.slack_board_intent import (
    looks_like_slack_board_config_question,
    looks_like_slack_board_request,
)
from backend.routing.tool_planner import looks_like_repo_doc_question, plan_tools_rules


_CONFIG_QUESTION = "can you see if this is configured to track and assign tasks?"


def test_config_status_matches_board_intent():
    assert looks_like_slack_board_config_question(_CONFIG_QUESTION)
    assert looks_like_slack_board_request(_CONFIG_QUESTION)


def test_config_status_not_repo_doc_on_slack():
    assert not looks_like_repo_doc_question(_CONFIG_QUESTION, source="slack")


def test_config_status_admin_handler(tmp_path):
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C_TMP",
        raw_text=_CONFIG_QUESTION,
        cleaned_intent=_CONFIG_QUESTION,
    )
    response = try_slack_board_admin_command(
        task, AlfredConfig(slack=SlackConfig(enabled=True)), tmp_path
    )
    assert response is not None
    text = response.payload.data.get("text") or ""
    assert "Not configured" in text or "Board binding" in text


def test_config_status_does_not_plan_repo_docs(tmp_path):
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C_TMP",
        raw_text=_CONFIG_QUESTION,
        cleaned_intent=_CONFIG_QUESTION,
    )
    entities = extract_entities(task.cleaned_intent, task.raw_text, "")
    plan = plan_tools_rules(
        task,
        entities,
        skill_allowed=["search_repo_docs", "read_repo_doc", "slack_board_search_tasks"],
        config=AlfredConfig(slack=SlackConfig(enabled=True)),
        data_dir=tmp_path,
        entity_direct_only=True,
    )
    assert plan is None or plan.intent_class != "repo.docs.qa"
