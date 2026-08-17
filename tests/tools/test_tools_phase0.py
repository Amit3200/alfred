"""Phase 0 tests for new JIRA and Google tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.ai.base import ToolSchema
from backend.models.config import AlfredConfig, GoogleConfig, JiraConfig
from backend.tools.google.sheets.register import register_sheet_tools
from backend.tools.jira.register import JIRA_ASSIGN_ISSUE, register_jira_tools
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult


def test_catalog_includes_phase0_tools():
    from backend.tools.catalog import ALL_KNOWN_TOOLS, tool_domain

    assert "google_create_sheet" in ALL_KNOWN_TOOLS
    assert "jira_assign_issue" in ALL_KNOWN_TOOLS
    assert tool_domain("google_create_sheet") == "google_sheet"
    assert tool_domain("jira_assign_issue") == "jira"


def test_jira_assign_issue_tool():
    config = AlfredConfig(
        jira=JiraConfig(
            enabled=True,
            base_url="https://example.atlassian.net/",
            email="a@example.com",
            api_token="token",
        )
    )
    registry = ToolRegistry()
    mock_client = MagicMock()
    mock_client.assign_issue.return_value = {
        "key": "ENG-1",
        "assignee": "Alice",
        "url": "https://example.atlassian.net/browse/ENG-1",
        "action": "assign",
    }

    with patch("backend.tools.jira.register.JiraApiClient.from_alfred_config", return_value=mock_client), patch(
        "backend.domains.jira.service.JiraApiClient.from_alfred_config",
        return_value=mock_client,
    ):
        register_jira_tools(registry, config)

        assert "jira_assign_issue" in registry._tools
        schema = registry._tools["jira_assign_issue"].schema
        assert schema.name == "jira_assign_issue"

        result = registry.run(
            "jira_assign_issue",
            {"issue_key": "ENG-1", "assignee": "alice@example.com"},
            allowed=["jira_assign_issue"],
        )
    assert result.kind == "jira_action"
    assert result.data["action"] == "assign"
    mock_client.assign_issue.assert_called_once_with("ENG-1", assignee="alice@example.com")


def test_google_create_sheet_tool():
    registry = ToolRegistry()
    register_sheet_tools(
        registry,
        credentials_json='{"type":"service_account","project_id":"x"}',
        refresh_token="",
    )
    assert "google_create_sheet" in registry._tools

    with patch("backend.tools.google.sheets.tools.google_libs_available", return_value=True):
        with patch("backend.tools.google.sheets.tools.google_sheets.create_spreadsheet") as create:
            create.return_value = {
                "spreadsheet_id": "abc123",
                "title": "Report",
                "url": "https://docs.google.com/spreadsheets/d/abc123/edit",
                "row_count": 2,
            }
            result = registry.run(
                "google_create_sheet",
                {"title": "Report", "headers": ["A", "B"], "rows": [["1", "2"]]},
                allowed=["google_create_sheet"],
            )

    assert result.kind == "google_sheet"
    assert result.data["action"] == "create"
    assert result.data["url"] == "https://docs.google.com/spreadsheets/d/abc123/edit"


def test_iter_tool_bundles_includes_migrated_domains():
    from backend.tools.base.discover import iter_tool_bundles

    names = {n for bundle in iter_tool_bundles() for n in bundle.tool_names()}
    for expected in (
        "get_pr",
        "grep_repo",
        "create_pull_request",
        "query_graph",
        "google_create_sheet",
        "google_create_doc",
        "athena_query",
        "web_search",
        "run_company_script",
        "slack_fetch_thread",
        "jira_create_issue",
        "slack_board_create_task",
    ):
        assert expected in names, expected


def test_unified_runner_delegates_react_and_autonomous():
    from backend.agent.loop import run_agent_loop
    from backend.agent.runner import run_agent
    from backend.orchestrator.hermes_runner import run_hermes_loop

    provider = MagicMock()
    provider.chat.return_value = MagicMock(content="done", tool_calls=[])

    registry = ToolRegistry()
    schema = ToolSchema(
        name="grep_repo",
        description="grep",
        parameters={"type": "object", "properties": {}, "required": []},
    )
    registry.register(schema, lambda _a: ToolResult(kind="text", data={"text": "ok"}))

    messages = [__import__("backend.ai.base", fromlist=["Message"]).Message(role="user", content="hi")]

    assert run_agent_loop(provider, messages, registry, ["grep_repo"]) == "done"
    assert run_hermes_loop(provider, messages, registry, ["grep_repo"]) == "done"
    assert run_agent(provider, messages, registry, ["grep_repo"], mode="autonomous") == "done"
