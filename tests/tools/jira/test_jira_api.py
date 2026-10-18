"""Tests for JIRA API client."""

from __future__ import annotations
from backend.health import check_jira


from unittest.mock import MagicMock, patch

import pytest

from backend.integrations.jira.api import JiraApiClient, extract_issue_key
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


@patch("backend.integrations.jira.api.requests.Session")
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


@patch("backend.integrations.jira.api.requests.Session")
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


@patch("backend.integrations.jira.api.requests.Session")
def test_create_issue_resilient_falls_back_when_reporter_invalid(mock_session_cls):
    session = MagicMock()
    mock_session_cls.return_value = session
    calls: list[dict] = []

    def fake_request(method, url, **kwargs):
        resp = MagicMock()
        if method == "GET" and url.endswith("/myself"):
            resp.status_code = 200
            resp.content = b'{"accountId":"token-user"}'
            resp.json.return_value = {"accountId": "token-user"}
            return resp
        if method == "GET" and "/user/search" in url:
            resp.status_code = 200
            resp.content = b"[]"
            resp.json.return_value = []
            return resp
        if method == "POST" and url.endswith("/issue"):
            fields = (kwargs.get("json") or {}).get("fields") or {}
            calls.append(fields)
            reporter = (fields.get("reporter") or {}).get("accountId")
            if reporter == "unknown-user":
                resp.status_code = 400
                resp.text = '{"errors":{"reporter":"invalid"}}'
                resp.json.return_value = {"errors": {"reporter": "invalid"}}
                resp.reason = "Bad Request"
                return resp
            resp.status_code = 201
            resp.content = b'{"key":"TS-9"}'
            resp.json.return_value = {"key": "TS-9"}
            return resp
        resp.status_code = 200
        resp.content = b"{}"
        resp.json.return_value = {}
        return resp

    session.request.side_effect = fake_request

    client = JiraApiClient(_config().jira, api_token="secret")
    client._token_account_id = "token-user"
    client.resolve_account_id = MagicMock(side_effect=lambda ident: "unknown-user" if ident else None)

    result = client.create_issue(
        project="TS",
        summary="Test ticket",
        issue_type="Task",
        reporter="External Person",
        resilient=True,
    )
    assert result["key"] == "TS-9"
    assert any((c.get("reporter") or {}).get("accountId") == "token-user" for c in calls)


@patch("backend.integrations.jira.api.requests.Session")
def test_create_issue_resilient_drops_assignee_on_failure(mock_session_cls):
    session = MagicMock()
    mock_session_cls.return_value = session

    def fake_request(method, url, **kwargs):
        resp = MagicMock()
        if method == "GET" and url.endswith("/myself"):
            resp.status_code = 200
            resp.content = b'{"accountId":"token-user"}'
            resp.json.return_value = {"accountId": "token-user"}
            return resp
        if method == "POST" and url.endswith("/issue"):
            fields = (kwargs.get("json") or {}).get("fields") or {}
            if fields.get("assignee"):
                resp.status_code = 400
                resp.text = '{"errors":{"assignee":"invalid"}}'
                resp.json.return_value = {"errors": {"assignee": "invalid"}}
                resp.reason = "Bad Request"
                return resp
            resp.status_code = 201
            resp.content = b'{"key":"TS-10"}'
            resp.json.return_value = {"key": "TS-10"}
            return resp
        resp.status_code = 200
        resp.content = b"[]"
        resp.json.return_value = []
        return resp

    session.request.side_effect = fake_request

    client = JiraApiClient(_config().jira, api_token="secret")
    client._token_account_id = "token-user"
    client.resolve_account_id = MagicMock(return_value="bad-assignee")

    result = client.create_issue(
        project="TS",
        summary="Test",
        issue_type="Task",
        assignee="Nobody",
        resilient=True,
    )
    assert result["key"] == "TS-10"


@patch("backend.integrations.jira.api.requests.Session")
def test_create_issue_retries_invalid_issuetype_as_task(mock_session_cls):
    session = MagicMock()
    mock_session_cls.return_value = session

    def fake_request(method, url, **kwargs):
        resp = MagicMock()
        if method == "POST" and url.endswith("/issue"):
            fields = (kwargs.get("json") or {}).get("fields") or {}
            kind = ((fields.get("issuetype") or {}).get("name") or "")
            if kind != "Task":
                resp.status_code = 400
                resp.text = '{"errors":{"issuetype":"Specify a valid issue type"}}'
                resp.json.return_value = {"errors": {"issuetype": "Specify a valid issue type"}}
                resp.reason = "Bad Request"
                return resp
            resp.status_code = 201
            resp.content = b'{"key":"TECH-12"}'
            resp.json.return_value = {"key": "TECH-12"}
            return resp
        resp.status_code = 200
        resp.content = b"{}"
        resp.json.return_value = {}
        return resp

    session.request.side_effect = fake_request
    client = JiraApiClient(_config().jira, api_token="secret")
    client._token_account_id = None
    client.resolve_account_id = MagicMock(return_value=None)
    client.token_account_id = MagicMock(return_value=None)

    result = client.create_issue(
        project="TECH",
        summary="Discount display",
        issue_type="Bug",
        resilient=True,
    )
    assert result["key"] == "TECH-12"
    assert result["issue_type"] == "Task"


def test_check_jira_disabled():
    pass

    config = AlfredConfig()
    result = check_jira(config)
    assert result["skipped"] is True
