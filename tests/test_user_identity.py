"""Tests for Slack ↔ JIRA user identity routing."""

from __future__ import annotations

from backend.routing.jira_context import detect_jira_list_action
from backend.routing.jira_direct import detect_jira_direct_action
from backend.integrations.identity.user_identity import (
    detect_user_identity_action,
    format_user_identity_result,
    is_user_identity_lookup,
    is_workspace_identity_request,
    list_slack_human_members,
    _match_github_login,
)
from backend.models.config import AlfredConfig, JiraConfig
from backend.models.task import Task


def _task(*, raw: str, cleaned: str) -> Task:
    return Task(
        source="slack",
        user_id="UAMIT",
        channel_id="C1",
        thread_ts="1.0",
        raw_text=raw,
        cleaned_intent=cleaned,
    )


def test_is_user_identity_lookup():
    intent = (
        "get me name of person, slack email_id, jira email_id, "
        "jira name, slack handle via which they get tagged"
    )
    assert is_user_identity_lookup(intent)
    assert not is_user_identity_lookup("list open jira tickets assigned to Om")


def test_identity_lookup_not_routed_to_jira_search():
    config = AlfredConfig()
    config.jira = JiraConfig(enabled=True, default_project="TECH")
    task = _task(
        raw="@alfred get slack email and jira email for user",
        cleaned="get slack email and jira email for user",
    )
    assert detect_jira_list_action(task.cleaned_intent, config, task) is None


def test_identity_lookup_direct_route():
    config = AlfredConfig()
    config.jira = JiraConfig(enabled=True)
    task = _task(
        raw="<@UALICE|Alice Smith> slack email jira email jira name slack handle",
        cleaned="slack email jira email jira name slack handle",
    )
    action = detect_jira_direct_action(task.cleaned_intent, config, task)
    assert action is not None
    assert action[0] == "lookup_user_identity"
    assert action[1]["slack_user_id"] == "UALICE"


def test_format_user_identity_result_includes_assignee_map():
    text = format_user_identity_result(
        {
            "identities": [
                {
                    "display_name": "Alice Smith",
                    "slack_user_id": "UALICE",
                    "slack_display_name": "Alice Smith",
                    "slack_email": "alice@example.com",
                    "jira_display_name": "Alice Smith",
                    "jira_email": "alice@example.com",
                }
            ],
            "assignee_map_suggestion": {"Alice Smith": "alice@example.com", "UALICE": "alice@example.com"},
        }
    )
    assert "assignee_map" in text
    assert "alice@example.com" in text


def test_workspace_identity_request_routes_to_bulk_tool():
    config = AlfredConfig()
    config.jira = JiraConfig(enabled=True)
    task = _task(
        raw="@alfred map all slack users to jira and github",
        cleaned="map all slack users to jira and github",
    )
    assert is_workspace_identity_request(task.cleaned_intent)
    action = detect_jira_direct_action(task.cleaned_intent, config, task)
    assert action == ("build_workspace_identity_map", {"include_github": True})


def test_list_slack_human_members_skips_bots():
    class FakeClient:
        def auth_test(self):
            return {"ok": True, "user_id": "UBOT"}

        def users_list(self, *, limit: int, cursor: str | None):
            return {
                "ok": True,
                "members": [
                    {"id": "UBOT", "is_bot": True, "profile": {"display_name": "alfred"}},
                    {
                        "id": "U1",
                        "is_bot": False,
                        "name": "om",
                        "real_name": "Alice Smith",
                        "profile": {"display_name": "Alice Smith", "email": "alice@example.com"},
                    },
                ],
            }

    members, error = list_slack_human_members(FakeClient())
    assert error is None
    assert len(members) == 1
    assert members[0]["id"] == "U1"


def test_match_github_login_by_slack_handle():
    entry = {"slack_handle": "alice-smith", "slack_email": "alice@example.com"}
    org_members = [{"login": "alice-smith"}, {"login": "other-dev"}]
    assert _match_github_login(entry, org_members) == "alice-smith"


def test_format_workspace_identity_result():
    text = format_user_identity_result(
        {
            "workspace": True,
            "count": 2,
            "matched_jira": 1,
            "matched_github": 1,
            "identities": [
                {
                    "display_name": "Alice Smith",
                    "slack_user_id": "U1",
                    "slack_handle": "om",
                    "slack_email": "alice@example.com",
                    "jira_email": "alice@example.com",
                    "github_login": "alice-smith",
                }
            ],
            "assignee_map_suggestion": {"Alice Smith": "alice@example.com"},
        }
    )
    assert "Workspace identity map" in text
    assert "alice@example.com" in text
    assert "alice-smith" in text
