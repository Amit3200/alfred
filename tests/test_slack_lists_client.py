"""Tests for Slack Lists API client helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from backend.integrations.slack.lists_client import list_columns
from backend.integrations.slack.board_service import _field_payload, _resolve_title_column


def test_list_columns_uses_items_info_schema():
    client = MagicMock()
    client.api_call.side_effect = [
        {
            "ok": True,
            "items": [{"id": "Rec001"}],
        },
        {
            "ok": True,
            "list": {
                "list_metadata": {
                    "schema": [
                        {
                            "id": "Col1",
                            "name": "Name",
                            "key": "name",
                            "type": "text",
                            "is_primary_column": True,
                        },
                        {
                            "id": "Col2",
                            "name": "Assignee",
                            "key": "assignee",
                            "type": "assignee",
                        },
                    ]
                }
            },
        },
    ]
    schema = list_columns(client, "F0LIST001")
    assert len(schema) == 2
    assert schema[0]["name"] == "Name"
    client.api_call.assert_any_call(
        "slackLists.items.list",
        json={"list_id": "F0LIST001", "limit": 1},
    )
    client.api_call.assert_any_call(
        "slackLists.items.info",
        json={"list_id": "F0LIST001", "id": "Rec001"},
    )


def test_list_columns_falls_back_to_files_info():
    client = MagicMock()
    client.api_call.side_effect = [
        {"ok": True, "items": []},
        {
            "ok": True,
            "file": {
                "list_metadata": {
                    "schema": [
                        {"id": "Col1", "name": "Title", "key": "title", "type": "text"},
                    ]
                }
            },
        },
    ]
    schema = list_columns(client, "F0LIST002")
    assert schema[0]["key"] == "title"
    client.api_call.assert_any_call("files.info", json={"file": "F0LIST002"})


def test_field_payload_uses_rich_text_for_text_columns():
    column = {"id": "Col1", "key": "name", "type": "text"}
    payload = _field_payload(column, "Smoke test")
    assert payload["column_id"] == "Col1"
    assert payload["key"] == "name"
    assert payload["rich_text"][0]["elements"][0]["elements"][0]["text"] == "Smoke test"
    assert "text" not in payload


def test_field_payload_assignee_uses_user_array():
    column = {"id": "Col2", "key": "assignee", "type": "assignee"}
    payload = _field_payload(column, "", user_ids=["U123"])
    assert payload["user"] == ["U123"]


def test_resolve_title_column_prefers_primary():
    schema = [
        {"id": "Col1", "name": "Notes", "key": "notes", "type": "rich_text"},
        {"id": "Col2", "name": "Name", "key": "name", "type": "text", "is_primary_column": True},
    ]
    col = _resolve_title_column(schema, "Ticket Details")
    assert col is not None
    assert col["key"] == "name"
