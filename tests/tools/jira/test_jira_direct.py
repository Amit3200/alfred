"""Tests for JIRA direct routing."""

from __future__ import annotations

from backend.routing.jira.direct import detect_jira_direct_action, looks_like_jira_question
from backend.models.config import AlfredConfig, JiraConfig


def test_looks_like_jira_question():
    assert looks_like_jira_question("what is the status of ENG-42")
    assert looks_like_jira_question("open jira tickets in ENG")
    assert looks_like_jira_question("create the above ticket in TS board")
    assert not looks_like_jira_question("hello there")


def test_detect_jira_direct_get_issue():
    config = AlfredConfig()
    config.jira = JiraConfig(enabled=True, base_url="https://x.atlassian.net", email="a@b.com")
    action = detect_jira_direct_action("status of ENG-99", config)
    assert action == ("get_jira_issue", {"issue_key": "ENG-99"})
