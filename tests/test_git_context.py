"""Tests for session git context helpers."""

from __future__ import annotations

from backend.ingress.git_context import (
    collect_thread_git_hints,
    detect_investigate_direct_action,
    enrich_tool_arguments,
    format_session_git_context,
    wants_git_retry,
)
from backend.models.config import GitConfig
from backend.models.session import ConversationSession
from backend.tools.result import ToolResult


def _session(**metadata) -> ConversationSession:
    return ConversationSession(
        key="ui:1:1",
        source="ui",
        scope_id="1",
        thread_id="1",
        metadata=metadata,
    )


def test_wants_git_retry():
    assert wants_git_retry("please retry above")
    assert not wants_git_retry("review this pr")


def test_collect_thread_git_hints_finds_file_line():
    hints = collect_thread_git_hints("see `order_handler.py:42` in FlexyPe/backend")
    assert hints["file_lines"] == [{"path": "order_handler.py", "line": 42}]
    assert "FlexyPe/backend" in hints["repos"]


def test_format_session_git_context_includes_active_pr():
    session = _session(
        active_pr={
            "repo": "FlexyPe/backend",
            "number": 91,
            "head": "feature/foo",
        },
        last_git_action={"tool": "grep_repo", "args": {"repo": "FlexyPe/backend"}},
    )
    block = format_session_git_context(session, "what does it do?")
    assert "Active PR: #91" in block
    assert "feature/foo" in block
    assert "Last git tool" in block


def test_detect_investigate_where_is():
    git = GitConfig(enabled=True, provider="github", token="x", default_org="FlexyPe")
    action = detect_investigate_direct_action(
        "where is duplicate order handled in flexype-backend?",
        "investigate_bug",
        git,
        None,
    )
    assert action is not None
    tool, args = action
    assert tool == "grep_repo"
    assert args["repo"] == "FlexyPe/flexype-backend"
    assert "duplicate" in args["pattern"]
    assert "order" in args["pattern"]


def test_detect_investigate_replays_last_action():
    git = GitConfig(enabled=True, provider="github", token="x")
    session = _session(
        last_git_action={
            "tool": "grep_repo",
            "args": {"repo": "acme/backend", "pattern": "foo"},
        }
    )
    action = detect_investigate_direct_action("retry above", "investigate_bug", git, session)
    assert action == ("grep_repo", {"repo": "acme/backend", "pattern": "foo"})


def test_enrich_tool_arguments_fills_ref_from_active_pr():
    git = GitConfig(enabled=True, provider="github", token="x", default_org="FlexyPe")
    session = _session(active_pr={"repo": "FlexyPe/backend", "number": 1, "head": "pr-branch"})
    args = enrich_tool_arguments("grep_repo", {"repo": "backend", "pattern": "x"}, git, session)
    assert args["repo"] == "FlexyPe/backend"
    assert args["ref"] == "pr-branch"


def test_metadata_patch_for_get_pr():
    from backend.ingress.git_context import metadata_patch_for_tool_result

    result = ToolResult.pr_detail(
        {
            "repo": "acme/backend",
            "number": 5,
            "head": "feat",
            "base": "main",
            "title": "Fix",
            "url": "https://example.com/pull/5",
        }
    )
    patch = metadata_patch_for_tool_result("get_pr", {"repo": "acme/backend", "number": 5}, result)
    assert patch is not None
    assert patch["active_pr"]["number"] == 5
    assert patch["last_git_action"]["tool"] == "get_pr"
