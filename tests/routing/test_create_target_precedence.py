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
    assert persona_prefers_jira_creates(
        "Use JIRA project=TECH when asked to create a ticket. "
        "Fall back to the Slack List if JIRA fails."
    )
    assert persona_prefers_jira_creates(
        "When creating tickets, prefer JIRA project key TECH."
    )
    assert not persona_prefers_jira_creates("")
    assert not persona_prefers_jira_creates(
        "This is billing support. Prefer invoice docs. Do not create tickets unless asked."
    )
    assert not persona_prefers_jira_creates(
        "Answer from docs. Do not create JIRA tickets for basic queries."
    )


TEAM_TECH_JIRA_PERSONA = """You are Acme engineering support in #team-tech.

## When to create
Create a ticket ONLY when the user asks to create / open / log / raise / file a task, ticket, or issue.
Do NOT create on small talk, thanks, status pings, or docs/how-to questions. Answer those instead.
If they are updating an existing ticket (status, assignee, or an explicit id), update that ticket. Do not create a new one.
If you are not sure whether they want a ticket, do not create. Ask one short clarifying question.

## Where to create
1. Primary: JIRA project key `TECH` (this is the TECH board). Always pass project=`TECH`. Never use board titles as the project (`TECH board`, `JIRA Tech Board`, `TECH-SUPPORT`).
2. Fallback: if `jira_create_issue` fails (bad project, permission, or API error), immediately create on this channel’s Slack List with `slack_board_create_task`. Do not retry JIRA with a guessed project name.
3. Do not create JIRA and Slack List for the same request unless JIRA failed and you are using the fallback.

## Description (required)
For JIRA, call `jira_create_issue` with:
- project: `TECH`
- issue_type: `Task` unless the user names Bug/Story
- summary: one-line problem
- description: always write a real body, not empty. Include:
  - What was asked / the problem
  - Why it matters or who is blocked (if known)
  - Any steps, IDs, or error text from the thread
  - Slack thread permalink

For the Slack List fallback, use a matching title and the same problem summary in details.

Reply with the JIRA key + URL, or the Slack List display id if you fell back. Say so if you used the fallback.
"""


def test_team_tech_persona_prefers_jira_despite_dual_write_sentence():
    assert persona_prefers_jira_creates(TEAM_TECH_JIRA_PERSONA)
    from backend.routing.jira.project_key import project_key_from_persona

    assert project_key_from_persona(TEAM_TECH_JIRA_PERSONA) == "TECH"


def test_team_tech_persona_routes_generic_create_to_jira(tmp_path):
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
        persona_prompt=TEAM_TECH_JIRA_PERSONA,
    )
    intent = "create a task to have variant based PPCOD selection"
    assert should_route_create_to_jira(
        intent,
        jira_enabled=True,
        channel_id="C_TECH",
        data_dir=tmp_path,
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


def test_persona_overrides_leftover_session_slack_list(tmp_path):
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
            "Use JIRA project=TECH when asked to create a ticket. "
            "Fall back to the Slack List if JIRA fails."
        ),
    )
    intent = "create a task to have variant based PPCOD selection"
    assert should_route_create_to_jira(
        intent,
        jira_enabled=True,
        channel_id="C_TECH",
        data_dir=tmp_path,
        session_metadata={"ticket_create_target": "slack_list"},
    )
    assert not looks_like_slack_board_create(
        intent,
        channel_id="C_TECH",
        data_dir=tmp_path,
        session_metadata={"ticket_create_target": "slack_list"},
    )


def test_followup_create_in_jira_400_thread_routes_to_jira():
    intent = "create a task to have variant based PPCOD selection"
    thread = (
        "[1] Azeem Hussain: @alfred create a task on JIRA Tech Board "
        "to have variant based PPCOD selection\n"
        "[2] bot: JIRA API 400: The target project doesn't exist or you don't have permission\n"
        "[5] Amit: the above took JIRA Tech as the board name.\n"
    )
    assert should_route_create_to_jira(
        intent,
        jira_enabled=True,
        thread_context=thread,
    )
    assert not looks_like_slack_board_create(intent, thread_context=thread)


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
        persona_prompt="You are Acme support. Prefer docs. Do not create tickets unless asked.",
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
