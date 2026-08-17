"""Tests for JIRA context and assignee resolution."""

from __future__ import annotations

from unittest.mock import MagicMock

from backend.routing.jira.context import (
    build_open_assigned_jql,
    detect_jira_list_action,
    format_jira_context_for_prompt,
    jira_project_keys,
    jira_projects_for_task,
    resolve_assignees_for_task,
    resolve_jira_assignee,
    resolve_jira_project_for_task,
    resolve_project_alias,
    wants_current_user,
)
from backend.models.config import AlfredConfig, JiraConfig, SlackListJiraSyncConfig
from backend.models.task import Task


def _task(*, raw: str, cleaned: str, user_id: str = "UAMIT", channel_id: str = "C1") -> Task:
    return Task(
        source="slack",
        user_id=user_id,
        channel_id=channel_id,
        thread_ts="1.0",
        raw_text=raw,
        cleaned_intent=cleaned,
    )


def test_jira_project_keys_defaults_to_default_project():
    config = JiraConfig(default_project="TECH", allowed_projects=[])
    assert jira_project_keys(config) == ["TECH"]


def test_jira_project_keys_uses_allowed_when_set():
    config = JiraConfig(default_project="TECH", allowed_projects=["ENG", "tech"])
    assert jira_project_keys(config) == ["ENG", "TECH"]


def test_wants_current_user():
    assert wants_current_user("list my open jira tickets")
    assert wants_current_user("tickets assigned to me")
    assert not wants_current_user("open tickets assigned to Om")


def test_resolve_jira_assignee_from_map():
    config = AlfredConfig()
    config.jira = JiraConfig(
        enabled=True,
        assignee_map={"Alice Smith": "alice@example.com"},
    )
    client = MagicMock()
    assert resolve_jira_assignee("Alice Smith", config, client) == "alice@example.com"
    client.search_users.assert_not_called()


def test_resolve_jira_assignee_via_search():
    config = AlfredConfig()
    config.jira = JiraConfig(enabled=True)
    client = MagicMock()
    client.search_users.return_value = [
        {"displayName": "Alice Smith", "emailAddress": "alice@example.com"},
    ]
    assert resolve_jira_assignee("Alice Smith", config, client) == "alice@example.com"


def test_resolve_assignees_from_slack_mention_label():
    config = AlfredConfig()
    config.jira = JiraConfig(
        enabled=True,
        assignee_map={"Alice Smith": "alice@example.com"},
    )
    task = _task(
        raw="<@UALICE123|Alice Smith> give me open tickets assigned to",
        cleaned="give me open tickets assigned to",
        user_id="UAMIT",
    )
    client = MagicMock()
    assignees = resolve_assignees_for_task(task, config, client)
    assert assignees == ["alice@example.com"]
    client.search_users.assert_not_called()


def test_resolve_assignees_skips_current_user_when_other_named():
    config = AlfredConfig()
    config.jira = JiraConfig(
        enabled=True,
        assignee_map={"Alice Smith": "alice@example.com"},
    )
    task = _task(
        raw="<@UALICE|Alice Smith> list open tickets assigned to",
        cleaned="list open tickets assigned to",
    )
    client = MagicMock()
    assignees = resolve_assignees_for_task(task, config, client)
    assert assignees == ["alice@example.com"]
    assert "currentUser()" not in assignees


def test_build_open_assigned_jql_with_project_and_assignee():
    jql = build_open_assigned_jql(["alice@example.com"], ["TECH"])
    assert 'project = "TECH"' in jql
    assert 'assignee = "alice@example.com"' in jql
    assert "status not in" in jql


def test_detect_jira_list_action_for_named_assignee(monkeypatch):
    config = AlfredConfig()
    config.jira = JiraConfig(
        enabled=True,
        base_url="https://acme.atlassian.net",
        email="bob@example.com",
        default_project="TECH",
        assignee_map={"Alice Smith": "alice@example.com"},
    )
    task = _task(
        raw="<@UALICE|Alice Smith> give me all open tickets assigned to",
        cleaned="give me all open tickets assigned to",
    )

    class FakeClient:
        @classmethod
        def from_alfred_config(cls, cfg):
            return cls()

        def search_users(self, *a, **k):
            return []

    monkeypatch.setattr("backend.routing.jira.context.JiraApiClient", FakeClient)
    action = detect_jira_list_action(task.cleaned_intent, config, task)
    assert action is not None
    tool, args = action
    assert tool == "jira_search"
    assert 'project = "TECH"' in args["jql"]
    assert 'assignee = "alice@example.com"' in args["jql"]
    assert "currentUser()" not in args["jql"]


def test_detect_jira_list_action_uses_channel_project_map(monkeypatch):
    config = AlfredConfig()
    config.jira = JiraConfig(
        enabled=True,
        base_url="https://acme.atlassian.net",
        email="bob@example.com",
        default_project="TECH",
        channel_projects={"C_TECH": "TS"},
    )
    task = _task(
        raw="@alfred list all open jira tickets",
        cleaned="list all open jira tickets which are not done yet",
        channel_id="C_TECH",
    )

    class FakeClient:
        @classmethod
        def from_alfred_config(cls, cfg):
            return cls()

        def search_users(self, *a, **k):
            return []

    monkeypatch.setattr("backend.routing.jira.context.JiraApiClient", FakeClient)
    action = detect_jira_list_action(task.cleaned_intent, config, task)
    assert action is not None
    _, args = action
    assert 'project = "TS"' in args["jql"]
    assert 'project = "TECH"' not in args["jql"]


def test_detect_jira_list_action_honors_explicit_ts_board(monkeypatch):
    config = AlfredConfig()
    config.jira = JiraConfig(
        enabled=True,
        base_url="https://acme.atlassian.net",
        email="bob@example.com",
        default_project="TECH",
        project_aliases={"ts board": "TS", "on ts": "TS"},
    )
    task = _task(
        raw="@alfred list jira tickets on TS board",
        cleaned="list all jira tickets not done yet on TS board",
    )

    class FakeClient:
        @classmethod
        def from_alfred_config(cls, cfg):
            return cls()

        def search_users(self, *a, **k):
            return []

    monkeypatch.setattr("backend.routing.jira.context.JiraApiClient", FakeClient)
    action = detect_jira_list_action(task.cleaned_intent, config, task)
    assert action is not None
    _, args = action
    assert 'project = "TS"' in args["jql"]


def test_resolve_project_alias_from_config():
    config = JiraConfig(
        project_aliases={
            "tech-support": "TS",
            "ts board": "TS",
            "tech board": "TECH",
        }
    )
    assert resolve_project_alias("list tickets on TS board", config) == "TS"
    assert resolve_project_alias("move to tech board", config) == "TECH"
    assert resolve_project_alias("check tech-support queue", config) == "TS"
    assert resolve_project_alias("hello world", config) is None


def test_jira_projects_for_task_prefers_intent_over_channel():
    config = AlfredConfig()
    config.jira = JiraConfig(
        enabled=True,
        default_project="TECH",
        channel_projects={"C1": "TS"},
        project_aliases={"tech board": "TECH"},
    )
    task = _task(
        raw="list TECH board tickets",
        cleaned="list open tickets on TECH board",
        channel_id="C1",
    )
    assert jira_projects_for_task(task, config) == ["TECH"]


def test_scope_jql_replaces_wrong_project_for_channel():
    from backend.routing.jira.context import scope_jql_for_task

    config = AlfredConfig()
    config.jira = JiraConfig(
        enabled=True,
        default_project="TECH",
        channel_projects={"C_TECH": "TS"},
    )
    config.slack.list_jira_sync = SlackListJiraSyncConfig(
        enabled=True,
        jira_project="TS",
        channel_ids=["C_TECH"],
    )
    task = _task(
        raw="@alfred list tickets on TS board",
        cleaned="list all jira tickets on TS board",
        channel_id="C_TECH",
    )
    scoped = scope_jql_for_task(
        'project = "TECH" AND status not in ("Done") ORDER BY updated DESC',
        task,
        config,
    )
    assert 'project = "TS"' in scoped
    assert 'project = "TECH"' not in scoped


def test_format_jira_context_includes_resolved_assignee(monkeypatch):
    config = AlfredConfig()
    config.jira = JiraConfig(
        enabled=True,
        base_url="https://acme.atlassian.net",
        email="bob@example.com",
        default_project="TECH",
        assignee_map={"Alice Smith": "alice@example.com"},
    )
    task = _task(
        raw="<@UALICE|Alice Smith> open tickets assigned to",
        cleaned="open tickets assigned to",
    )

    class FakeClient:
        @classmethod
        def from_alfred_config(cls, cfg):
            return cls()

        def search_users(self, *a, **k):
            return []

    monkeypatch.setattr("backend.routing.jira.context.JiraApiClient", FakeClient)
    prompt = format_jira_context_for_prompt(config, task)
    assert "Resolved assignee" in prompt
    assert "alice@example.com" in prompt
    assert "Default project scope" in prompt
    assert "TECH" in prompt


def test_resolve_assignees_via_slack_user_info(monkeypatch):
    from backend.routing.jira.context import _slack_user_info

    config = AlfredConfig()
    config.slack.enabled = True
    config.slack.bot_token = "xoxb-dummy"
    config.jira.enabled = True

    mock_client = MagicMock()
    mock_client.users_info.return_value = {
        "ok": True,
        "user": {
            "id": "U12345",
            "real_name": "Charlie Chaplin",
            "name": "charlie",
            "profile": {"email": "charlie@chaplin.com"},
        },
    }

    monkeypatch.setattr("backend.routing.jira.context.WebClient", lambda token: mock_client)

    display, email = _slack_user_info("U12345", config)
    assert display == "Charlie Chaplin"
    assert email == "charlie@chaplin.com"
