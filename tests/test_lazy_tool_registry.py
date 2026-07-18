"""Tests for lazy tool registration by skill allowlist."""

from __future__ import annotations

from backend.models.config import AWSConfig, AlfredConfig, GitConfig, JiraConfig, WebSearchConfig
from backend.tools.catalog import AWS_TOOLS, GIT_API_TOOLS, GIT_LOCAL_TOOLS, JIRA_TOOLS, WEB_TOOLS
from backend.tools.git_api import build_git_tool_registry


def _full_config(**overrides) -> AlfredConfig:
    config = AlfredConfig()
    config.git = GitConfig(enabled=True, token="ghp_test", provider="github")
    config.jira = JiraConfig(enabled=True, base_url="https://x.atlassian.net", email="a@b.com", api_token="tok")
    config.aws = AWSConfig(enabled=True, region="us-east-1")
    config.web_search = WebSearchConfig(enabled=True)
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def test_lazy_registry_registers_only_jira_tools():
    registry = build_git_tool_registry(
        _full_config(),
        allowed_tools=["get_jira_issue"],
    )
    names = set(registry._tools.keys())
    assert names == {"get_jira_issue"}


def test_lazy_registry_registers_only_git_local_tools(tmp_path):
    registry = build_git_tool_registry(
        _full_config(),
        data_dir=tmp_path,
        workspace_id="ui:test:test",
        allowed_tools=["grep_repo", "read_file"],
    )
    names = set(registry._tools.keys())
    assert names == {"grep_repo", "read_file"}
    assert not names & JIRA_TOOLS
    assert not names & AWS_TOOLS


def test_lazy_registry_skips_git_api_client_when_not_needed():
    registry = build_git_tool_registry(
        _full_config(),
        allowed_tools=["athena_query"],
    )
    names = set(registry._tools.keys())
    assert names <= AWS_TOOLS
    assert not names & GIT_API_TOOLS
    assert not names & GIT_LOCAL_TOOLS


def test_lazy_registry_web_search_only():
    registry = build_git_tool_registry(
        _full_config(),
        allowed_tools=["web_search"],
    )
    assert set(registry._tools.keys()) == {"web_search"}


def test_full_registry_when_allowed_tools_none():
    registry = build_git_tool_registry(_full_config())
    names = set(registry._tools.keys())
    assert "get_jira_issue" in names
    assert "list_my_prs" in names
    assert "athena_query" in names
