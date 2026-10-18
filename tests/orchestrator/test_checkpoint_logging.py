"""Tests for checkpoint-based logging."""

from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO

from backend.observability.checkpoint import log_checkpoint


def test_log_checkpoint_started():
    f = StringIO()
    with redirect_stdout(f):
        log_checkpoint("jira_tool_call", "abc", "started")

    output = f.getvalue().strip()
    data = json.loads(output)

    assert data["checkpoint"] == "jira_tool_call"
    assert data["function_name"] == "abc"
    assert data["status"] == "started"
    assert "timestamp" in data
    assert isinstance(data["timestamp"], float)


def test_log_checkpoint_error():
    f = StringIO()
    exc = ValueError("something went wrong")
    try:
        raise exc
    except ValueError as e:
        with redirect_stdout(f):
            log_checkpoint("jira_tool_call", "abc", "error", error=e)

    output = f.getvalue().strip()
    data = json.loads(output)

    assert data["checkpoint"] == "jira_tool_call"
    assert data["function_name"] == "abc"
    assert data["status"] == "error"
    assert data["error"] == "ValueError"
    assert "ValueError: something went wrong" in data["error_stacktrace"]
