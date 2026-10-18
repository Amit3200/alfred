"""Tests for JIRA agent tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.models.config import AlfredConfig, JiraConfig
from backend.tools.builder import build_git_tool_registry
from backend.tools.result import ToolResult


def _config() -> AlfredConfig:
    config = AlfredConfig()
    config.jira = JiraConfig(
        enabled=True,
        base_url="https://example.atlassian.net",
        email="dev@example.com",
        api_token="secret",
        default_project="ENG",
    )
    return config


@patch("backend.domains.jira.service.JiraApiClient")
def test_get_jira_issue_tool(mock_client_cls):
    client = MagicMock()
    mock_client_cls.from_alfred_config.return_value = client
    client.get_issue.return_value = {
        "key": "ENG-1",
        "summary": "Test",
        "status": "Open",
        "url": "https://example.atlassian.net/browse/ENG-1",
    }

    registry = build_git_tool_registry(_config())
    result = registry.run("get_jira_issue", {"issue_key": "ENG-1"}, allowed=["get_jira_issue"])

    assert isinstance(result, ToolResult)
    assert result.kind == "jira_detail"
    assert result.data["issue"]["key"] == "ENG-1"


@patch("backend.domains.jira.service.JiraApiClient")
def test_jira_search_tool(mock_client_cls):
    client = MagicMock()
    mock_client_cls.from_alfred_config.return_value = client
    client.search_issues.return_value = []

    registry = build_git_tool_registry(_config())
    result = registry.run(
        "jira_search",
        {"jql": "assignee = currentUser()"},
        allowed=["jira_search"],
    )

    assert result.kind == "jira_list"
    client.search_issues.assert_called_once()


@patch("backend.domains.jira.service.JiraApiClient")
def test_jira_create_issue_tool(mock_client_cls):
    client = MagicMock()
    mock_client_cls.from_alfred_config.return_value = client
    client.create_issue.return_value = {
        "key": "ENG-99",
        "url": "https://example.atlassian.net/browse/ENG-99",
        "summary": "New task",
        "issue_type": "Task",
        "project": "ENG",
    }

    registry = build_git_tool_registry(_config())
    result = registry.run(
        "jira_create_issue",
        {"project": "ENG", "summary": "New task", "issue_type": "Task"},
        allowed=["jira_create_issue"],
    )

    assert result.kind == "jira_action"
    assert result.data["action"] == "create"
    assert result.data["key"] == "ENG-99"


@patch("backend.domains.jira.service.JiraApiClient")
def test_jira_create_defaults_uncertain_issue_type_to_task(mock_client_cls):
    client = MagicMock()
    mock_client_cls.from_alfred_config.return_value = client
    client.create_issue.return_value = {
        "key": "TECH-1",
        "url": "https://example.atlassian.net/browse/TECH-1",
        "summary": "Discount display",
        "issue_type": "Task",
        "project": "TECH",
    }

    registry = build_git_tool_registry(_config())
    result = registry.run(
        "jira_create_issue",
        {"project": "TECH", "summary": "Discount display", "issue_type": "Ticket"},
        allowed=["jira_create_issue"],
    )

    assert result.kind == "jira_action"
    req = client.create_issue.call_args.kwargs
    assert req["issue_type"] == "Task"


@patch("backend.domains.jira.service.JiraApiClient")
def test_link_jira_issue_tool(mock_client_cls):
    client = MagicMock()
    mock_client_cls.from_alfred_config.return_value = client
    client.link_remote.return_value = {
        "key": "ENG-1",
        "url": "https://github.com/org/repo/pull/1",
        "title": "PR #1",
    }

    registry = build_git_tool_registry(_config())
    result = registry.run(
        "link_jira_issue",
        {"issue_key": "ENG-1", "url": "https://github.com/org/repo/pull/1"},
        allowed=["link_jira_issue"],
    )

    assert result.kind == "jira_action"
    assert result.data["action"] == "link"
