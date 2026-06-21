"""Tests for Slack output formatting."""

from backend.ingress.slack_format import format_for_slack


def test_double_bold_to_slack():
    assert format_for_slack("**Failed Deployments**") == "*Failed Deployments*"


def test_markdown_heading_to_slack_bold():
    assert format_for_slack("### Summary\n\nHello") == "*Summary*\n\nHello"


def test_markdown_table_converted_to_code_block():
    raw = "| Category | Count |\n| --- | --- |\n| CPU alerts | 1 |\n| RabbitMQ | 4 |"
    out = format_for_slack(raw)
    assert "```" in out
    assert "CPU alerts" in out
    assert "RabbitMQ" in out
    assert "• CPU alerts" not in out


def test_fenced_code_block_preserved():
    raw = "Summary\n```\nDate | Merchant\n2026-06-17 | ExampleStore\n```\nDone"
    out = format_for_slack(raw)
    assert "Date" in out
    assert "Merchant" in out
    assert "ExampleStore" in out


def test_table_without_trailing_pipe():
    raw = "| RabbitMQ | 7\n| CPU threshold | 1"
    out = format_for_slack(raw)
    assert "```" in out
    assert "RabbitMQ" in out
