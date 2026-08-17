"""Tests for Slack board intent parsing."""

from __future__ import annotations

from backend.routing.slack_board_intent import (
    extract_severity_target,
    extract_task_title,
    extract_ticket_ref,
    looks_like_slack_board_create,
    looks_like_slack_board_request,
    looks_like_slack_board_update,
    references_thread_context,
    resolve_ticket_ref,
)


def test_create_task_for_above_title():
    intent = "create task for payment timeout on checkout for above"
    assert looks_like_slack_board_create(intent)
    assert references_thread_context(intent)
    assert extract_task_title(intent) == "payment timeout on checkout"


def test_create_task_on_title():
    intent = "create a task on working on the revamping the AI as p0"
    assert looks_like_slack_board_create(intent)
    assert "revamping" in extract_task_title(intent).lower()


def test_create_task_to_title():
    intent = "create a task to talk to CottonThreads"
    assert looks_like_slack_board_create(intent)
    assert extract_task_title(intent) == "talk to CottonThreads"


def test_create_task_dash_title():
    intent = "create a task - Smoke Test Integration of slack"
    assert looks_like_slack_board_create(intent)
    assert extract_task_title(intent) == "Smoke Test Integration of slack"


def test_create_task_colon_title():
    intent = "create task: merchant onboarding follow-up"
    assert extract_task_title(intent) == "merchant onboarding follow-up"


def test_board_create_title_followup():
    from backend.routing.slack_board_intent import (
        extract_board_title_followup,
        looks_like_board_create_title_followup,
    )

    assert looks_like_board_create_title_followup(
        "Talk to CottonThreads",
        session_turns=("What should the task be called?",),
    )
    assert extract_board_title_followup("@alfred Talk to CottonThreads") == "Talk to CottonThreads"


def test_assign_it_to_detects_board_update():
    intent = "assign it to @user"
    assert looks_like_slack_board_update(intent)


def test_create_task_simple():
    assert looks_like_slack_board_create("please create task for merchant sync failure")
    assert extract_task_title("create task for merchant sync failure") == "merchant sync failure"


def test_board_request_and_ticket_ref():
    intent = "move TS-42 to in progress"
    assert looks_like_slack_board_request(intent)
    assert looks_like_slack_board_update(intent)
    assert extract_ticket_ref(intent) == "TS-42"


def test_update_detects_assign_this_task():
    intent = "assign this task to @user"
    assert looks_like_slack_board_update(intent)
    assert not looks_like_slack_board_create(intent)


def test_update_detects_st_prefix_inline_status():
    intent = "ST-1 is in progress and assign severity to High. Also assign it to @user"
    assert looks_like_slack_board_update(intent)
    assert extract_ticket_ref(intent) == "ST-1"


def test_update_detects_slack_board_context():
    intent = "Update (slack board sales-tracker) ST-1 is in progress"
    assert looks_like_slack_board_update(intent)
    assert extract_ticket_ref(intent) == "ST-1"


def test_display_prefix_update_not_board_task_update():
    intent = "update the Display Prefix to ST"
    assert not looks_like_slack_board_update(intent)


def test_extract_severity_target():
    intent = "ST-1 is in progress and assign severity to High"
    assert extract_severity_target(intent) == "High"
    assert extract_severity_target("create task as p0 for outage") == "High"
    assert extract_severity_target("set priority to p3") == "Low"


def test_build_board_task_details_filters_setup_noise():
    from backend.routing.slack_board_intent import build_board_task_details

    raw = "\n".join(
        [
            "[1] 2026-08-09 16:22 UTC | user: setup board for the team-sales",
            "[2] 2026-08-09 16:23 UTC | bot (app): Created and linked Slack List",
            "[3] 2026-08-09 16:24 UTC | user: Smoke Test Integration of slack",
        ]
    )
    details = build_board_task_details(
        messages_text=raw,
        channel_id="C123",
        thread_ts="1234567890.123456",
        team_id="T051RLW5NLR",
        task_title="Smoke Test Integration of slack",
    )
    assert "Summary: Smoke Test Integration of slack" in details
    assert "slack.com/client/T051RLW5NLR/C123/thread/" in details
    assert "Created and linked Slack List" not in details
    assert "setup board" not in details.lower() or "Summary:" in details


def test_grounding_slack_board_hides_internal_issues():
    from backend.routing.goal_spec import GoalSpec
    from backend.routing.grounding_gate import validate_agent_result

    result = validate_agent_result(
        "Create a Slack List task to talk to CottonThreads on the sales-tracker board.",
        [],
        GoalSpec(
            intent_class="slack.board.create",
            goal="Create task",
            requires_write=True,
        ),
    )
    assert not result.passed
    assert "Issues:" not in result.fallback
    assert "create task for" in result.fallback.lower()


def test_resolve_ticket_ref_from_session():
    ref = resolve_ticket_ref(
        "assign this task to @user",
        session_metadata={"last_board_task": {"display_id": "TS-9", "record_id": "Rec1"}},
    )
    assert ref == "TS-9"
