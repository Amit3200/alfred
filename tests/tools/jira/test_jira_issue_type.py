from backend.domains.jira.issue_type import (
    is_issuetype_error,
    resolve_jira_create_issue_type,
)
from backend.models.config import AlfredConfig, JiraConfig


def test_empty_and_ticket_fall_back_to_task():
    assert resolve_jira_create_issue_type("") == "Task"
    assert resolve_jira_create_issue_type("ticket") == "Task"
    assert resolve_jira_create_issue_type("Issue") == "Task"
    assert resolve_jira_create_issue_type("TECH board") == "Task"


def test_explicit_bug_and_story_are_kept():
    assert resolve_jira_create_issue_type("Bug") == "Bug"
    assert resolve_jira_create_issue_type("Story") == "Story"


def test_project_mapping_overrides_empty():
    config = AlfredConfig(jira=JiraConfig(project_issue_types={"TS": "Process"}))
    assert resolve_jira_create_issue_type("", project="TS", config=config) == "Process"
    assert resolve_jira_create_issue_type("ticket", project="TS", config=config) == "Process"


def test_issuetype_error_detection():
    assert is_issuetype_error("JIRA API 400: issuetype: Specify a valid issue type")
    assert not is_issuetype_error("JIRA API 400: assignee: invalid")
