"""Tests for direct Git routing and text tool-call parsing."""

from __future__ import annotations
from backend.routing.git_direct import looks_like_code_investigation
from backend.models.config import GitConfig
from backend.routing.git_direct import wants_pr_code_analysis
from backend.integrations.git.api import resolve_repo_slug
from backend.routing.git_direct import normalize_tool_arguments


from backend.routing.git_direct import (
    detect_git_direct_action,
    extract_pr_reference,
    looks_like_tool_json,
    normalize_tool_arguments,
    parse_text_tool_call,
    wants_pr_summary,
)
from backend.routing.playbooks import Playbook
from pathlib import Path


def _git_skill() -> Playbook:
    return Playbook(
        name="git_status",
        path=Path("git_status.md"),
        body="",
        mode="investigation",
        allowed_tools=["list_my_prs", "list_prs", "get_pr", "list_repos"],
    )


def test_detect_my_open_prs():
    action = detect_git_direct_action("what are open PRs of mine?", _git_skill())
    assert action == ("list_my_prs", {"state": "open"})


def test_detect_my_prs_variant():
    action = detect_git_direct_action("are there any open prs of mine?", _git_skill())
    assert action is not None
    assert action[0] == "list_my_prs"


def test_detect_repo_prs():
    action = detect_git_direct_action("open prs on myorg/backend", _git_skill())
    assert action == ("list_prs", {"repo": "myorg/backend", "state": "open"})


def test_parse_malformed_text_tool_call():
    raw = '{"name":"list_my_prs","parameters{"state"": "open"}}'
    parsed = parse_text_tool_call(raw)
    assert parsed is not None
    assert parsed[0] == "list_my_prs"
    assert parsed[1]["state"] == "open"


def test_parse_valid_text_tool_call():
    raw = '{"name": "list_my_prs", "parameters": {"state": "open"}}'
    assert parse_text_tool_call(raw) == ("list_my_prs", {"state": "open"})


def test_parse_kimi_tool_tag():
    raw = (
        "I'll search.\n\n"
        '<tool>{"tool_type": "function", "tool_name": "grep_repo", '
        '"tool_input": {"pattern": "recalculation", "path": "AcmeCorp/platform"}}</tool>'
    )
    parsed = parse_text_tool_call(raw)
    assert parsed == ("grep_repo", {"pattern": "recalculation", "path": "AcmeCorp/platform"})


def test_looks_like_code_investigation():
    pass

    assert looks_like_code_investigation(
        "Can you tell what does recalculation method does? what are steps of it?"
    )
    assert not looks_like_code_investigation("hello there")


def test_looks_like_tool_json_with_tool_tag():
    raw = 'Intro\n<tool>{"tool_name":"grep_repo","tool_input":{}}</tool>'
    assert looks_like_tool_json(raw)


def test_extract_pr_from_slack_link():
    intent = (
        "summarize what this PR does - "
        "<https://github.com/AcmeCorp/adhocs/pull/91|#91 Feat: SQS Consumer Sup>"
    )
    ref = extract_pr_reference(intent)
    assert ref == ("AcmeCorp/adhocs", 91)


def test_detect_get_pr_from_url():
    pass

    intent = "can you summarize what this PR does - https://github.com/AcmeCorp/platform/pull/1685"
    action = detect_git_direct_action(intent, _git_skill(), GitConfig(default_org="AcmeCorp"))
    assert action == ("get_pr", {"repo": "AcmeCorp/platform", "number": 1685})


def test_wants_pr_summary():
    assert wants_pr_summary("can you summarize what this PR does")
    assert not wants_pr_summary("list my open prs")


def test_wants_pr_code_analysis():
    pass

    assert wants_pr_code_analysis(
        "review https://github.com/AcmeCorp/adhocs/pull/91"
    )
    assert not wants_pr_code_analysis("summarize my open prs")


def test_resolve_repo_slug_with_default_org():
    pass
    pass

    git = GitConfig(default_org="AcmeCorp", repos=["AcmeCorp/adhocs"])
    assert resolve_repo_slug("adhocs", git) == "AcmeCorp/adhocs"


def test_normalize_tool_arguments_short_repo():
    pass
    pass

    git = GitConfig(default_org="AcmeCorp")
    args = normalize_tool_arguments("get_pr", {"repo": "adhocs", "number": 91}, git)
    assert args["repo"] == "AcmeCorp/adhocs"


def test_looks_like_tool_json():
    assert looks_like_tool_json('{"name":"list_my_prs","parameters":{}}')
    assert not looks_like_tool_json("Here are your PRs")
