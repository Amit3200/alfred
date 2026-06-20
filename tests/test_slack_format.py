"""Tests for Slack output formatting."""

from backend.ingress.slack_format import format_for_slack


def test_double_bold_to_slack():
    assert format_for_slack("**Failed Deployments**") == "*Failed Deployments*"


def test_markdown_heading_to_slack_bold():
    assert format_for_slack("### Summary\n\nHello") == "*Summary*\n\nHello"


def test_linkify_bare_github_pr_url():
    text = "• https://github.com/org/repo/pull/42"
    result = format_for_slack(text)
    assert "<https://github.com/org/repo/pull/42|#42>" in result
