"""Tests for Slack List vs JIRA create routing precedence."""

from __future__ import annotations

from backend.models.config import AlfredConfig, JiraConfig
from backend.routing.create_target_precedence import (
    persona_prefers_jira_creates,
    should_route_create_to_jira,
)
from backend.routing.jira.intent import looks_like_jira_create_request
from backend.routing.slack_board.intent import looks_like_slack_board_create


def test_explicit_jira_create_task_routes_to_jira_not_slack_board():
    intent = "create a task to add freebie using coupon in JIRA on TECH board"
    assert looks_like_jira_create_request(intent)
    assert should_route_create_to_jira(intent, jira_enabled=True)
    assert not looks_like_slack_board_create(intent)


def test_slack_board_create_still_matches_without_jira():
    intent = "create a task for payment delay on the board"
    assert looks_like_slack_board_create(intent)
    assert not should_route_create_to_jira(intent, jira_enabled=True)


def test_create_task_for_all_the_above_issues_stays_on_slack_board():
    intent = "create a task for all the above issues"
    assert looks_like_slack_board_create(intent)
    assert not looks_like_jira_create_request(intent)
    assert not should_route_create_to_jira(intent, jira_enabled=True)


def test_create_all_following_tasks_stays_on_slack_board_despite_jira_session():
    intent = (
        "can you create all the following tasks, each item is separate task\n"
        "• Exit reason to be given on Export file\n"
        "• Snapchat Integration"
    )
    assert looks_like_slack_board_create(intent)
    assert not should_route_create_to_jira(
        intent,
        jira_enabled=True,
        session_turns=("Failed jira_create_issue — Governance: requires explicit approval",),
    )


def test_jira_followup_after_thread_context():
    intent = "yup go ahead and create"
    session = (
        "Governance: jira_create_issue requires explicit approval",
        "create this on JIRA dashboard with TECH board",
    )
    assert should_route_create_to_jira(
        intent,
        jira_enabled=True,
        session_turns=session,
    )


def test_ticket_create_target_metadata_prefers_jira():
    intent = "create a task for coupon freebie"
    assert should_route_create_to_jira(
        intent,
        jira_enabled=True,
        session_metadata={"ticket_create_target": "jira"},
    )


def test_channel_jira_policy_routes_generic_create_to_jira(tmp_path):
    from backend.db.slack_workflows_db import db_upsert_channel_workflow

    db_upsert_channel_workflow(
        tmp_path,
        channel_id="C_TECH",
        ticket_system="jira",
        jira_project_key="TECH",
    )
    intent = "create a task to have variant based PPCOD selection"
    assert should_route_create_to_jira(
        intent,
        jira_enabled=True,
        channel_id="C_TECH",
        data_dir=tmp_path,
    )


def test_persona_prefers_jira_from_natural_language():
    assert persona_prefers_jira_creates(
        "Create tickets on the TECH board in JIRA whenever asked. "
        "Fall back to the Slack List if JIRA fails."
    )
    assert persona_prefers_jira_creates(
        "Primary: call jira_create_issue with project=`TECH`."
    )
    assert not persona_prefers_jira_creates("")
    assert not persona_prefers_jira_creates(
        "This is billing support. Prefer invoice docs. Do not create tickets unless asked."
    )
    assert not persona_prefers_jira_creates(
        "Answer from docs. Do not create JIRA tickets for basic queries."
    )


def test_channel_persona_overrides_slack_list_default(tmp_path):
    from backend.db.slack_workflows_db import db_create_board_binding, db_upsert_channel_workflow

    db_upsert_channel_workflow(
        tmp_path,
        channel_id="C_TECH",
        ticket_system="slack_list",
        jira_project_key="TECH",
    )
    db_create_board_binding(
        tmp_path,
        board_key="team-tech",
        list_id="F1234567890",
        channel_id="C_TECH",
        persona_prompt=(
            "Create tickets on TECH board in JIRA whenever asked, "
            "then fall back on the Slack list board."
        ),
    )
    intent = "create a task to have variant based PPCOD selection"
    assert should_route_create_to_jira(
        intent,
        jira_enabled=True,
        channel_id="C_TECH",
        data_dir=tmp_path,
    )


def test_slack_list_default_without_jira_persona(tmp_path):
    from backend.db.slack_workflows_db import db_create_board_binding, db_upsert_channel_workflow

    db_upsert_channel_workflow(
        tmp_path,
        channel_id="C_TECH",
        ticket_system="slack_list",
    )
    db_create_board_binding(
        tmp_path,
        board_key="team-tech",
        list_id="F1234567890",
        channel_id="C_TECH",
        persona_prompt="You are FlexyPe support. Prefer docs. Do not create tickets unless asked.",
    )
    intent = "create a task to have variant based PPCOD selection"
    assert not should_route_create_to_jira(
        intent,
        jira_enabled=True,
        channel_id="C_TECH",
        data_dir=tmp_path,
    )


def test_explicit_slack_list_stays_on_board_despite_channel_jira(tmp_path):
    from backend.db.slack_workflows_db import db_upsert_channel_workflow

    db_upsert_channel_workflow(
        tmp_path,
        channel_id="C_TECH",
        ticket_system="jira",
        jira_project_key="TECH",
    )
    intent = "create a task for PPCOD on the slack list"
    assert not should_route_create_to_jira(
        intent,
        jira_enabled=True,
        channel_id="C_TECH",
        data_dir=tmp_path,
    )


def test_tool_planner_jira_create_plan():
    from backend.models.task import Task
    from backend.routing.entity_extractor import EntityBag
    from backend.routing.tool_planner import plan_tools_rules

    config = AlfredConfig()
    config.jira = JiraConfig(enabled=True)
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        thread_ts="1.0",
        raw_text="create a task to add freebie using coupon in JIRA on TECH board",
        cleaned_intent="create a task to add freebie using coupon in JIRA on TECH board",
    )
    plan = plan_tools_rules(
        task,
        EntityBag(),
        skill_allowed=["jira_create_issue", "slack_board_create_task"],
        config=config,
    )
    assert plan is not None
    assert plan.intent_class == "jira.write.create"
    assert plan.tools_needed == ["jira_create_issue"]
