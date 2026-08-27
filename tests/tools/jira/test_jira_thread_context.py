"""JIRA create/update should use Slack thread context, not placeholders."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.domains.jira.thread_fields import (
    extract_update_body,
    fill_jira_create_args,
    fill_jira_update_args,
    is_weak_jira_summary,
)
from backend.models.config import AlfredConfig, JiraConfig
from backend.models.task import Task
from backend.orchestrator.policy import needs_context_refresh
from backend.routing.classifier.classify import classify_intent_rules
from backend.routing.entity_extractor import extract_entities
from backend.routing.jira.intent import looks_like_jira_update_request
from backend.routing.tool_planner import plan_tools_rules
from backend.tools.builder import build_git_tool_registry
from backend.tools.result import ToolResult

_THREAD = """
[1] Kushagra: Merchant: Everaw Nutrition (c7ccd6-a0.myshopify.com)
Issue: The merchant has reported an issue with how the Prepaid Discount is displayed in the order summary.
[2] alfred: Created TS-24 — Incorrect Prepaid Discount Display in Order Summary
[3] Kushagra: @alfred can you create a ticket on TECH board on jira
"""

_DETAILS = """
Merchant: Everaw Nutrition (c7ccd6-a0.myshopify.com)
Issue: The merchant has reported an issue with how the Prepaid Discount is displayed in the order summary.

Please check:
1. Why the prepaid discount shows as a negative value
2. Whether the order summary template is wrong
, using this pls update TECH-363
"""


def _config() -> AlfredConfig:
    config = AlfredConfig()
    config.jira = JiraConfig(
        enabled=True,
        base_url="https://example.atlassian.net",
        email="dev@example.com",
        api_token="secret",
        default_project="TECH",
    )
    return config


def _task(text: str) -> Task:
    return Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        thread_ts="1.0",
        raw_text=text,
        cleaned_intent=text,
    )


def test_placeholder_and_board_command_are_weak_summaries():
    assert is_weak_jira_summary("<to be provided by user>")
    assert is_weak_jira_summary("can you create a ticket on TECH board on jira")
    assert is_weak_jira_summary("TECH board on jira")
    assert not is_weak_jira_summary("Incorrect Prepaid Discount Display in Order Summary")


def test_create_fills_summary_and_description_from_thread():
    filled = fill_jira_create_args(
        {
            "summary": "<to be provided by user>",
            "description": "<optional details from user>",
            "project": "TECH",
            "issue_type": "Task",
        },
        request_text="@alfred can you create a ticket on TECH board on jira",
        thread_text=_THREAD,
    )
    assert "Prepaid Discount" in filled["summary"]
    assert "Everaw" in filled["description"]
    assert "<to be provided by user>" not in filled["summary"]
    assert "<optional details from user>" not in filled["description"]


def test_update_uses_pasted_details_and_normalizes_space_key():
    assert looks_like_jira_update_request("please modify TECH 363 with proper details")
    assert looks_like_jira_update_request("using this pls update TECH-363")
    body = extract_update_body(_DETAILS)
    assert "Everaw" in body
    assert "update TECH-363" not in body

    filled = fill_jira_update_args(
        {"issue_key": "TECH 363", "summary": "<to be provided by user>"},
        request_text=_DETAILS,
        thread_text=_THREAD,
    )
    assert "Prepaid Discount" in filled["summary"]
    assert "Everaw" in filled["description"]
    assert filled["replace_description"] is True


def test_tech_space_key_extracted():
    bag = extract_entities("please modify TECH 363 with proper details")
    assert bag.issue_keys == ("TECH-363",)


def test_create_and_update_refresh_slack_context():
    assert needs_context_refresh(
        "can you create a ticket on TECH board on jira",
        has_session=True,
    )
    assert needs_context_refresh(
        "please modify TECH 363 with proper details",
        has_session=True,
    )


def test_rules_classify_modify_as_jira_update():
    result = classify_intent_rules(
        _task("please modify TECH 363 with proper details"),
        config=_config(),
    )
    assert result.intent_class == "jira.write.update"
    assert result.entities["issue_key"] == "TECH-363"


def test_rules_classify_tech_board_create():
    result = classify_intent_rules(
        _task("@alfred can you create a ticket on TECH board on jira"),
        config=_config(),
    )
    assert result.intent_class == "jira.write.create"


def test_plan_update_uses_jira_update_issue():
    task = _task("please modify TECH 363 with proper details")
    plan = plan_tools_rules(
        task,
        extract_entities(task.cleaned_intent),
        skill_allowed=["jira_update_issue", "get_jira_issue"],
        config=_config(),
    )
    assert plan is not None
    assert plan.tools_needed == ["jira_update_issue"]
    assert plan.intent_class == "jira.write.update"


@patch("backend.domains.jira.thread_fields.fetch_slack_thread_text", return_value=_THREAD)
@patch("backend.domains.jira.service.JiraApiClient")
def test_create_tool_rejects_placeholder_without_thread_and_fills_with_thread(
    mock_client_cls,
    mock_fetch,
):
    client = MagicMock()
    mock_client_cls.from_alfred_config.return_value = client
    client.create_issue.return_value = {
        "key": "TECH-363",
        "url": "https://example.atlassian.net/browse/TECH-363",
        "summary": "The merchant has reported an issue with how the Prepaid Discount is displayed in the order summary.",
        "issue_type": "Task",
        "project": "TECH",
    }
    registry = build_git_tool_registry(_config())
    registry.current_task = _task("@alfred can you create a ticket on TECH board on jira")
    result = registry.run(
        "jira_create_issue",
        {
            "project": "TECH",
            "summary": "<to be provided by user>",
            "issue_type": "Task",
            "description": "<optional details from user>",
        },
        allowed=["jira_create_issue"],
    )
    assert isinstance(result, ToolResult)
    assert result.kind == "jira_action"
    called = client.create_issue.call_args.kwargs
    assert "Prepaid Discount" in called["summary"]
    assert "Everaw" in (called.get("description") or "") or "Prepaid Discount" in (
        called.get("description") or ""
    )
    mock_fetch.assert_called()


@patch("backend.domains.jira.thread_fields.fetch_slack_thread_text", return_value="")
@patch("backend.domains.jira.service.JiraApiClient")
def test_create_tool_errors_on_placeholder_without_context(mock_client_cls, _mock_fetch):
    client = MagicMock()
    mock_client_cls.from_alfred_config.return_value = client
    registry = build_git_tool_registry(_config())
    result = registry.run(
        "jira_create_issue",
        {
            "project": "TECH",
            "summary": "<to be provided by user>",
            "issue_type": "Task",
        },
        allowed=["jira_create_issue"],
    )
    assert result.kind == "error"
    assert "placeholder" in str(result.data.get("message") or "").lower()
    client.create_issue.assert_not_called()
