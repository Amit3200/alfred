"""Tests for Slack List ticket enrichment."""

from __future__ import annotations

from unittest.mock import MagicMock

from backend.ingress.slack_lists import (
    enrich_channel_context_with_lists,
    extract_embedded_list_records,
    extract_list_refs,
    format_list_record,
    wants_slack_list_enrichment,
)
from backend.ingress.slack_messages import extract_message_text


def test_wants_slack_list_enrichment_for_ticket_summary():
    intent = "summarize open tickets last week by severity and category"
    assert wants_slack_list_enrichment(intent)


def test_extract_list_refs_from_slack_link():
    message = {
        "text": (
            "Submit a ticket (app): reported a "
            "<https://acme.slack.com/lists/T081ABC/F0A5AS3HF9S?record_id=Rec0BC2G4SQ1J|bug>"
        )
    }
    refs = extract_list_refs([message])
    assert refs == [("F0A5AS3HF9S", "Rec0BC2G4SQ1J")]


def test_format_list_record_with_severity_and_status():
    schema = [
        {"id": "Col0A578GSR8S", "name": "Name", "key": "name", "type": "text"},
        {"id": "Col0A53RE4HL5", "name": "Severity", "key": "Col07QKE8AVP0", "type": "select",
         "options": {"choices": [
             {"value": "OptT6D4G0LP", "label": "High"},
             {"value": "OptYYB79DT0", "label": "Medium"},
         ]}},
        {"id": "Col0A50SUEY91", "name": "Status", "key": "Col07QP7FEP4M", "type": "select",
         "options": {"choices": [
             {"value": "OptLKAALRN6", "label": "Not picked"},
             {"value": "OptWFPDVRZC", "label": "In progress"},
         ]}},
    ]
    record = {
        "record_id": "Rec0BC2G4SQ1J",
        "fields": [
            {"key": "name", "text": "User blocked from COD placed a COD order", "column_id": "Col0A578GSR8S"},
            {"key": "Col07QKE8AVP0", "select": ["OptYYB79DT0"], "column_id": "Col0A53RE4HL5"},
            {"key": "Col07QP7FEP4M", "select": ["OptWFPDVRZC"], "column_id": "Col0A50SUEY91"},
            {"key": "Col07QP76TBQD", "text": "Merchant: Cotton Threads", "column_id": "Col0A4RR40AJK"},
        ],
    }
    text = format_list_record(record, schema=schema)
    assert "Severity: Medium" in text
    assert "Status: In progress" in text
    assert "Merchant: Cotton Threads" in text


def test_extract_embedded_list_records_from_attachment():
    message = {
        "attachments": [
            {
                "list_record_id": "Rec0BC2G4SQ1J",
                "list_record": {
                    "record": {
                        "record_id": "Rec0BC2G4SQ1J",
                        "fields": [
                            {"key": "name", "text": "Sample ticket"},
                            {"key": "Col07QKE8AVP0", "select": ["OptYYB79DT0"], "column_id": "Col0A53RE4HL5"},
                        ],
                    },
                    "schema": [
                        {"id": "Col0A53RE4HL5", "name": "Severity", "key": "Col07QKE8AVP0", "type": "select",
                         "options": {"choices": [{"value": "OptYYB79DT0", "label": "Medium"}]}},
                    ],
                },
            }
        ]
    }
    embedded = extract_embedded_list_records([message])
    assert embedded[0][0] == "Rec0BC2G4SQ1J"
    formatted = format_list_record(embedded[0][1], schema=embedded[0][2])
    assert "Severity: Medium" in formatted


def test_enrich_uses_embedded_records_without_api():
    client = MagicMock()
    messages = [
        {
            "attachments": [
                {
                    "list_record_id": "Rec0BC2G4SQ1J",
                    "list_record": {
                        "record": {
                            "record_id": "Rec0BC2G4SQ1J",
                            "fields": [
                                {"key": "name", "text": "Sample ticket"},
                                {"key": "Col07QKE8AVP0", "select": ["OptT6D4G0LP"], "column_id": "Col0A53RE4HL5"},
                            ],
                        },
                        "schema": [
                            {"id": "Col0A53RE4HL5", "name": "Severity", "key": "Col07QKE8AVP0", "type": "select",
                             "options": {"choices": [{"value": "OptT6D4G0LP", "label": "High"}]}},
                        ],
                    },
                }
            ]
        }
    ]
    result = enrich_channel_context_with_lists(
        client,
        messages,
        intent="classify by severity",
    )
    assert result is not None
    assert "Severity: High" in result
    client.api_call.assert_not_called()


def test_enrich_channel_context_with_lists_fetches_records():
    client = MagicMock()
    client.api_call.return_value = {
        "ok": True,
        "record": {
            "id": "Rec0BC2G4SQ1J",
            "fields": [
                {"key": "title", "value": "Sample ticket"},
                {"key": "severity", "value": "High"},
            ],
        },
    }
    messages = [
        {
            "text": (
                "<https://acme.slack.com/lists/T081ABC/F0A5AS3HF9S?record_id=Rec0BC2G4SQ1J|bug>"
            )
        }
    ]
    result = enrich_channel_context_with_lists(
        client,
        messages,
        intent="summarize tickets by severity",
    )
    assert result is not None
    assert "Slack List tickets" in result
    assert "Severity: High" in result
    client.api_call.assert_called_once_with(
        "slackLists.items.info",
        json={"list_id": "F0A5AS3HF9S", "id": "Rec0BC2G4SQ1J"},
    )


def test_extract_message_text_skips_raw_rich_text_json():
    message = {
        "text": (
            '[{"type":"rich_text","elements":[{"type":"rich_text_section",'
            '"elements":[{"type":"text","text":"User blocked from COD"}]}]}]'
        )
    }
    text = extract_message_text(message)
    assert "User blocked from COD" in text
    assert '"type":"rich_text"' not in text
