"""Phase 2 tests — GoalSpec, grounding gate, sync store."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from backend.integrations.sync.store import SyncStateStore
from backend.routing.goal_spec import goal_spec_from_plan
from backend.routing.grounding_gate import ToolTraceEntry, validate_agent_result
from backend.routing.tool_plan_types import ToolPlan
from backend.agent.subagents import group_steps_by_domain, should_use_subagents
from backend.routing.tool_plan_types import ToolPlanStep


def test_goal_spec_from_create_sheet_plan():
    plan = ToolPlan(
        goal="Create Google Sheet",
        confidence=0.9,
        tools_needed=["google_create_sheet", "google_write_sheet"],
        intent_class="google.create.sheet",
    )
    spec = goal_spec_from_plan(plan)
    assert spec is not None
    assert spec.requires_write
    assert "google_create_sheet" in spec.required_tools


def test_grounding_gate_rejects_fabricated_url():
    trace = [
        ToolTraceEntry(
            tool="get_jira_issue",
            success=True,
            result_kind="jira_detail",
            observation='{"key": "ENG-1", "url": "https://acme.atlassian.net/browse/ENG-1"}',
        )
    ]
    result = validate_agent_result(
        "Created sheet at https://evil.example/fake",
        trace,
        goal_spec_from_plan(
            ToolPlan(
                goal="test",
                confidence=0.9,
                tools_needed=["google_create_sheet"],
                intent_class="google.create.sheet",
            )
        ),
    )
    assert not result.passed
    assert result.fallback


def test_grounding_gate_allows_matching_url():
    url = "https://docs.google.com/spreadsheets/d/abc123/edit"
    trace = [
        ToolTraceEntry(
            tool="google_create_sheet",
            success=True,
            result_kind="google_sheet",
            observation=json.dumps({"spreadsheet_url": url}),
        )
    ]
    result = validate_agent_result(f"Sheet ready: {url}", trace, None)
    assert result.passed


def test_sync_state_store_stale(tmp_path: Path):
    store = SyncStateStore(tmp_path)
    assert store.is_stale("slack_users", hours=1)
    store.update("slack_users", {"user_count": 3})
    assert not store.is_stale("slack_users", hours=1)


def test_should_use_subagents_multi_domain():
    plan = ToolPlan(
        goal="Summarize and file",
        confidence=0.9,
        tools_needed=["slack_fetch_thread", "jira_create_issue", "jira_add_comment"],
        steps=[
            ToolPlanStep("slack_fetch_thread", "fetch"),
            ToolPlanStep("jira_create_issue", "create"),
            ToolPlanStep("jira_add_comment", "comment"),
        ],
        intent_class="mixed",
    )
    assert should_use_subagents(plan)
    groups = group_steps_by_domain(plan.steps)
    assert len(groups) >= 2


def test_sync_slack_users_skips_when_fresh(tmp_path: Path):
    from backend.integrations.sync.slack_users import sync_slack_users
    from backend.models.config import AlfredConfig, SlackConfig

    config = AlfredConfig(slack=SlackConfig(enabled=True, bot_token="x"))
    store = SyncStateStore(tmp_path)
    store.update("slack_users", {"user_count": 10})
    result = sync_slack_users(config, data_dir=tmp_path, force=False)
    assert result["ok"] is True
    assert result.get("skipped") is True
