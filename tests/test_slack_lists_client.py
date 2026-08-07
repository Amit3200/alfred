"""Tests for Slack Lists API client helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from slack_sdk.errors import SlackApiError

from backend.integrations.slack.board_service import _field_payload, _resolve_title_column
from backend.integrations.slack.lists_client import (
    SlackListAccessError,
    list_columns,
    verify_list_id,
)


def test_list_columns_prefers_files_info_schema():
    client = MagicMock()
    client.files_info.return_value = {
        "ok": True,
        "file": {
            "filetype": "list",
            "list_metadata": {
                "schema": [
                    {
                        "id": "Col1",
                        "name": "Name",
                        "key": "name",
                        "type": "text",
                        "is_primary_column": True,
                    },
                ]
            },
        },
    }
    schema = list_columns(client, "F0LIST001")
    assert len(schema) == 1
    assert schema[0]["name"] == "Name"
    client.files_info.assert_called_once_with(file="F0LIST001")
    client.api_call.assert_not_called()


def test_list_columns_falls_back_to_items_info():
    client = MagicMock()
    client.files_info.return_value = {
        "ok": True,
        "file": {"filetype": "list", "list_metadata": {"schema": []}},
    }
    client.api_call.side_effect = [
        {"ok": True, "items": [{"id": "Rec001"}]},
        {
            "ok": True,
            "list": {
                "list_metadata": {
                    "schema": [
                        {"id": "Col2", "name": "Assignee", "key": "assignee", "type": "assignee"},
                    ]
                }
            },
        },
    ]
    schema = list_columns(client, "F0LIST002")
    assert schema[0]["key"] == "assignee"


def test_list_columns_raises_when_list_missing():
    client = MagicMock()
    response = MagicMock()
    response.data = {"ok": False, "error": "list_not_found"}
    client.files_info.side_effect = SlackApiError(message="file_not_found", response=response)
    client.api_call.side_effect = SlackApiError(message="list_not_found", response=response)
    with pytest.raises(SlackListAccessError, match="F0MISSING"):
        list_columns(client, "F0MISSING")


def test_verify_list_id_accepts_when_schema_loads():
    client = MagicMock()
    client.auth_test.return_value = {"user_id": "UBOT"}
    client.api_call.side_effect = [
        {"ok": True},  # access.set bot
        {"ok": True},  # access.set channel
    ]
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "backend.integrations.slack.lists_client.list_columns",
            lambda _client, _lid: [
                {"id": "Col1", "name": "Name", "type": "text", "is_primary_column": True},
            ],
        )
        ok, msg = verify_list_id(client, "F0GOOD", channel_id="C1")
    assert ok is True
    assert msg == ""


def test_verify_list_id_rejects_missing_list():
    client = MagicMock()
    client.auth_test.return_value = {"user_id": "UBOT"}
    client.api_call.return_value = {"ok": True}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "backend.integrations.slack.lists_client.list_columns",
            lambda _client, _lid: (_ for _ in ()).throw(  # noqa: E731
                SlackListAccessError("Slack List `F0BAD` is not accessible (list not found).")
            ),
        )
        ok, msg = verify_list_id(client, "F0BAD", channel_id="C1")
    assert ok is False
    assert "F0BAD" in msg


def test_field_payload_uses_rich_text_for_text_columns():
    column = {"id": "Col1", "key": "name", "type": "text"}
    payload = _field_payload(column, "Smoke test")
    assert payload is not None
    assert payload == {
        "column_id": "Col1",
        "rich_text": [
            {
                "type": "rich_text",
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [{"type": "text", "text": "Smoke test"}],
                    }
                ],
            }
        ],
    }


def test_field_payload_omits_select_when_choice_unknown():
    column = {
        "id": "Col3",
        "type": "select",
        "options": {"choices": [{"value": "done", "label": "Done"}]},
    }
    assert _field_payload(column, "Not picked") is None


def test_field_payload_assignee_uses_user_array():
    column = {"id": "Col2", "key": "assignee", "type": "assignee"}
    payload = _field_payload(column, "", user_ids=["U123"])
    assert payload == {"column_id": "Col2", "user": ["U123"]}


def test_resolve_title_column_prefers_primary():
    schema = [
        {"id": "Col1", "name": "Notes", "key": "notes", "type": "rich_text"},
        {"id": "Col2", "name": "Name", "key": "name", "type": "text", "is_primary_column": True},
    ]
    col = _resolve_title_column(schema, "Ticket Details")
    assert col is not None
    assert col["key"] == "name"
