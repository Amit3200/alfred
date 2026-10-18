"""Tests for Slack List → JIRA auto-sync."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.integrations.slack.list_jira_sync import (
    should_handle_message_event,
    sync_channel_allowed,
    try_sync_list_message,
    _submitter_name,
)
from backend.models.config import AlfredConfig, JiraConfig, SlackConfig, SlackListJiraSyncConfig


def _workflow_event(*, status_value: str = "OptLKAALRN6", status_label: str = "Not picked") -> dict:
    schema = [
        {"id": "Col0A578GSR8S", "name": "Name", "key": "name", "type": "text"},
        {
            "id": "Col0A53RE4HL5",
            "name": "Severity",
            "key": "Col07QKE8AVP0",
            "type": "select",
            "options": {
                "choices": [
                    {"value": "OptT6D4G0LP", "label": "High"},
                    {"value": "OptYYB79DT0", "label": "Medium"},
                ]
            },
        },
        {
            "id": "Col0A50SUEY91",
            "name": "Status",
            "key": "Col07QP7FEP4M",
            "type": "select",
            "options": {
                "choices": [
                    {"value": "OptLKAALRN6", "label": "Not picked"},
                    {"value": "OptWFPDVRZC", "label": "In progress"},
                ]
            },
        },
        {"id": "Col0A4RR40AJK", "name": "Details", "key": "Col07QP76TBQD", "type": "text"},
        {"id": "Col0A4ISSUE01", "name": "Issue", "key": "Col07QISSUE01", "type": "text"},
    ]
    return {
        "type": "message",
        "subtype": "bot_message",
        "channel": "G012TECH",
        "ts": "1710000000.000100",
        "text": "<@U123> reported a bug",
        "attachments": [
            {
                "title": "Integration with delivery app is breaking",
                "list_record_id": "Rec0BC2G4SQ1J",
                "list_record": {
                    "list_id": "F0A5AS3HF9S",
                    "record": {
                        "record_id": "Rec0BC2G4SQ1J",
                        "fields": [
                            {
                                "key": "name",
                                "text": "Integration with delivery app is breaking",
                                "column_id": "Col0A578GSR8S",
                            },
                            {"key": "Col07QKE8AVP0", "select": ["OptYYB79DT0"], "column_id": "Col0A53RE4HL5"},
                            {"key": "Col07QP7FEP4M", "select": [status_value], "column_id": "Col0A50SUEY91"},
                            {
                                "key": "Col07QP76TBQD",
                                "text": "Merchant: QueensNdolls https://www.queensndolls.com/",
                                "column_id": "Col0A4RR40AJK",
                            },
                            {
                                "key": "Col07QISSUE01",
                                "text": "Unable to download invoice — access denied",
                                "column_id": "Col0A4ISSUE01",
                            },
                        ],
                    },
                    "schema": schema,
                },
            }
        ],
    }


def _config(*, enabled: bool = True) -> AlfredConfig:
    return AlfredConfig(
        initialized=True,
        slack=SlackConfig(
            enabled=True,
            allowed_channels=["*"],
            list_jira_sync=SlackListJiraSyncConfig(
                enabled=enabled,
                list_id="F0A5AS3HF9S",
                jira_project="TECH-SUPPORT",
                issue_type="Bug",
                eligible_statuses=["Not picked"],
            ),
        ),
        jira=JiraConfig(
            enabled=True,
            base_url="https://acme.atlassian.net",
            email="ops@example.com",
            default_project="TECH-SUPPORT",
        ),
    )


def test_should_handle_bot_workflow_message():
    event = _workflow_event()
    assert should_handle_message_event(event, bot_user_id="UBOT")


def test_should_ignore_message_changed():
    event = {"type": "message", "subtype": "message_changed", "channel": "G1"}
    assert not should_handle_message_event(event, bot_user_id="UBOT")


def test_sync_creates_jira_for_not_picked(tmp_path: Path):
    config = _config()
    jira = MagicMock()
    jira.create_issue.return_value = {
        "key": "TECH-SUPPORT-42",
        "url": "https://acme.atlassian.net/browse/TECH-SUPPORT-42",
    }
    result = try_sync_list_message(
        _workflow_event(),
        config,
        data_dir=tmp_path,
        jira_client=jira,
    )
    assert result.created
    assert result.jira_key == "TECH-SUPPORT-42"
    jira.create_issue.assert_called_once()
    call = jira.create_issue.call_args.kwargs
    assert call["project"] == "TECH-SUPPORT"
    assert call["issue_type"] == "Bug"
    assert call["priority"] == "Medium"
    assert call["resilient"] is True
    assert "Integration with delivery app" in call["summary"]
    assert "Unable to download invoice" in call["description"]
    assert "QueensNdolls" in call["description"]


def test_submitter_name_from_list_fields():
    fields = {"Submitted by": "Amit Singh Sansoya", "Name": "Test"}
    assert _submitter_name(fields, {}) == "Amit Singh Sansoya"


def test_sync_skips_in_progress_status(tmp_path: Path):
    config = _config()
    jira = MagicMock()
    result = try_sync_list_message(
        _workflow_event(status_value="OptWFPDVRZC", status_label="In progress"),
        config,
        data_dir=tmp_path,
        jira_client=jira,
    )
    assert result.skipped
    assert result.skip_reason.startswith("status_not_eligible")
    jira.create_issue.assert_not_called()


def test_sync_dedupes_same_record(tmp_path: Path):
    config = _config()
    jira = MagicMock()
    jira.create_issue.return_value = {"key": "TECH-SUPPORT-1", "url": "https://example.com/1"}
    event = _workflow_event()
    first = try_sync_list_message(event, config, data_dir=tmp_path, jira_client=jira)
    second = try_sync_list_message(event, config, data_dir=tmp_path, jira_client=jira)
    assert first.created
    assert second.skipped
    assert second.skip_reason == "already_synced"
    assert jira.create_issue.call_count == 1


def test_sync_channel_ids_override():
    config = _config()
    config.slack.list_jira_sync.channel_ids = ["G999"]
    assert not sync_channel_allowed("G012TECH", config)
    assert sync_channel_allowed("G999", config)
