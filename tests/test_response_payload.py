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


def test_response_payload_accepts_google_kinds():
    for kind in ("google_sheet", "google_doc"):
        payload = ResponsePayload(kind=kind, data={})
        assert payload.kind == kind


def test_assistant_response_structured_google_doc_create():
    response = AssistantResponse.structured(
        "google_doc",
        {"action": "create", "title": "2026-06-21/merchant/v0", "url": "https://docs.google.com/…"},
    )
    assert response.payload.kind == "google_doc"
