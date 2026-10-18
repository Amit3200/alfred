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


def test_connector_summary_does_not_fail_on_quoted_chat_urls():
    result = validate_agent_result(
        "Paytm webhook discussed: https://api.example.com/v1/public/pg/paytm/webhook",
        [
            ToolTraceEntry(
                tool="connector_get_messages",
                success=True,
                result_kind="connector_messages",
                observation='{"kind":"connector_messages","data":{"message_count":12,"chat_count":3}}',
            )
        ],
        goal_spec_from_plan(
            ToolPlan(
                goal="Fetch Periskope WhatsApp messages and summarize by chat",
                confidence=0.96,
                tools_needed=["connector_get_messages"],
                intent_class="connector.read.messages",
            )
        ),
    )
    assert result.passed


def test_format_partial_results_marks_script_fail_and_publish_ok():
    from backend.routing.grounding_gate import _format_partial_results

    script_obs = json.dumps(
        {
            "kind": "company_script_run",
            "data": {
                "script": "daily_metrics_oneshot",
                "runtime": "python3",
                "entry": "main.py",
                "exit_code": 1,
                "stdout": json.dumps(
                    {"status": "error", "exit_code": 1, "report_date": "2026-08-17"}
                ),
            },
        }
    )
    publish_obs = json.dumps(
        {
            "kind": "html_artifact_published",
            "data": {
                "slug": "daily-metrics",
                "title": "Daily metrics — 2026-08-17",
                "share_url": "/artifacts/s/daily-metrics",
                "slug_url": "/artifacts/s/daily-metrics",
            },
        }
    )
    text = _format_partial_results(
        [
            ToolTraceEntry(
                tool="run_company_script",
                success=True,
                result_kind="company_script_run",
                observation=script_obs,
            ),
            ToolTraceEntry(
                tool="publish_html_artifact",
                success=True,
                result_kind="html_artifact_published",
                observation=publish_obs,
            ),
        ]
    )
    assert "**Failed** `run_company_script`" in text
    assert "exited 1" in text
    assert "**Succeeded** `publish_html_artifact`" in text
    assert "/artifacts/s/daily-metrics" in text
    assert "1 failed" in text
    assert "1 succeeded" in text
    assert "Verified tool results" not in text
    assert script_obs[:80] not in text


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


def test_grounding_gate_allows_slack_mrkdwn_jira_browse_link():
    observation = json.dumps(
        {
            "kind": "jira_action",
            "data": {
                "action": "create",
                "key": "TECH-378",
                "url": "https://acme.atlassian.net/browse/TECH-378",
                "summary": "Implement variant-based PPCOD selection",
            },
        }
    )
    trace = [
        ToolTraceEntry(
            tool="jira_create_issue",
            success=True,
            result_kind="jira_action",
            observation=observation,
        )
    ]
    slack_reply = (
        "Created TECH-378 — Implement variant-based PPCOD selection.\n"
        "<https://acme.atlassian.net/browse/TECH-378|TECH-378>"
    )
    result = validate_agent_result(slack_reply, trace, None)
    assert result.passed

    encoded = (
        "Created TECH-378\n"
        "https://acme.atlassian.net/browse/TECH-378%7CTECH-378"
    )
    result = validate_agent_result(encoded, trace, None)
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
