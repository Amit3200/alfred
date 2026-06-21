"""Tests for AWS structured response rendering."""

from __future__ import annotations

from backend.ingress.render import render_for_channel
from backend.models.response import AssistantResponse, ResponsePayload


def test_render_cloudwatch_query_slack():
    response = AssistantResponse(
        payload=ResponsePayload(
            kind="cloudwatch_query",
            data={
                "log_group": "/ecs/api",
                "row_count": 1,
                "start_time": "2024-01-01T00:00:00+00:00",
                "end_time": "2024-01-01T01:00:00+00:00",
                "columns": ["message"],
                "rows": [{"message": "timeout error"}],
            },
        )
    )
    text = render_for_channel(response, "slack")
    assert "/ecs/api" in text
    assert "timeout error" in text


def test_render_athena_query_ui():
    response = AssistantResponse(
        payload=ResponsePayload(
            kind="athena_query",
            data={
                "database": "analytics",
                "row_count": 1,
                "columns": ["count"],
                "rows": [{"count": "42"}],
                "bytes_scanned": 1024,
                "query_execution_id": "q-1",
            },
        )
    )
    text = render_for_channel(response, "ui")
    assert "analytics" in text
    assert "42" in text
