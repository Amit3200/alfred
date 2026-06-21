"""Tests for JIRA API client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.jira.api import JiraApiClient, extract_issue_key
from backend.models.config import AlfredConfig, JiraConfig


def _config(**jira_kwargs) -> AlfredConfig:
    config = AlfredConfig()
    config.jira = JiraConfig(
        enabled=True,
        base_url="https://example.atlassian.net",
        email="dev@example.com",
        api_token="secret",
        default_project="ENG",
        **jira_kwargs,
    )
    return config


def test_extract_issue_key():
    assert extract_issue_key("status of ENG-123 please") == "ENG-123"
    assert extract_issue_key("no ticket here") is None


def test_issue_allowed_blocks_other_projects():
    client = JiraApiClient(_config(allowed_projects=["ENG"]).jira, api_token="secret")
    with pytest.raises(ValueError, match="allowed projects"):
        client._project_allowed("OPS")


@patch("backend.jira.api.requests.Session")
def test_search_issues_builds_jql(mock_session_cls):
    session = MagicMock()
    mock_session_cls.return_value = session
    session.request.return_value = MagicMock(
        status_code=200,
        content=b'{"issues": []}',
        json=lambda: {"issues": []},
    )

    client = JiraApiClient(_config().jira, api_token="secret")
    client.search_issues(project="ENG", status="Open")

    _, kwargs = session.request.call_args
    body = kwargs["json"]
    assert "project" in body["jql"]
    assert body["jql"].startswith('project = "ENG"')


@patch("backend.jira.api.requests.Session")
def test_transition_issue_picks_matching_status(mock_session_cls):
    session = MagicMock()
    mock_session_cls.return_value = session

    def fake_request(method, url, **kwargs):
        resp = MagicMock(status_code=200, content=b"{}")
        if method == "GET" and url.endswith("/transitions"):
            resp.json.return_value = {
                "transitions": [
                    {"id": "21", "name": "Start Review", "to": {"name": "In Review"}},
                ]
            }
        elif method == "POST" and url.endswith("/transitions"):
            resp.content = b""
            resp.json.return_value = {}
        elif method == "GET" and "/issue/ENG-9" in url:
            resp.json.return_value = {
                "key": "ENG-9",
                "fields": {
                    "summary": "Fix bug",
                    "status": {"name": "In Review"},
                    "issuetype": {"name": "Bug"},
                    "assignee": None,
                    "priority": None,
                    "labels": [],
                    "description": None,
                    "comment": {"total": 0},
                    "issuelinks": [],
                },
            }
        else:
            resp.json.return_value = []
        return resp

    session.request.side_effect = fake_request

    client = JiraApiClient(_config().jira, api_token="secret")
    result = client.transition_issue("ENG-9", transition="In Review")
    assert result["status"] == "In Review"


def test_check_jira_disabled():
    from backend.health import check_jira

    config = AlfredConfig()
    result = check_jira(config)
    assert result["skipped"] is True
