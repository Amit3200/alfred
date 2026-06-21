"""Tests for structured response payload kinds."""

from __future__ import annotations

from backend.models.response import AssistantResponse, ResponsePayload


def test_response_payload_accepts_jira_kinds():
    for kind in ("jira_list", "jira_detail", "jira_action"):
        payload = ResponsePayload(kind=kind, data={})
        assert payload.kind == kind


def test_response_payload_accepts_aws_kinds():
    for kind in ("athena_query", "cloudwatch_query", "cloudwatch_log_groups", "grade_events_query"):
        payload = ResponsePayload(kind=kind, data={})
        assert payload.kind == kind


def test_assistant_response_structured_jira_list():
    response = AssistantResponse.structured(
        "jira_list",
        {"issues": [{"key": "TECH-1", "summary": "Test"}]},
    )
    assert response.payload.kind == "jira_list"
