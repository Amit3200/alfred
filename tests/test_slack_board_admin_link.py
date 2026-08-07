"""Slack board admin link command tests."""

from __future__ import annotations

from unittest.mock import patch

from backend.db.slack_workflows_db import (
    db_create_board_binding,
    db_get_board_binding_for_channel,
    db_get_channel_workflow,
    db_upsert_channel_workflow,
)
from backend.integrations.slack.board_keys import derive_board_key
from backend.models.config import AlfredConfig, SlackConfig
from backend.models.task import Task
from backend.routing.slack_board_admin import try_slack_board_admin_command


def test_derive_board_key_from_channel_name():
    assert derive_board_key(channel_name="tmp-board-test") == "tmp-board-test"
    assert derive_board_key(channel_id="C0BNNSMGG91") == "board-nnsmgg91"


@patch("backend.routing.slack_board_admin.fetch_slack_channel_name", return_value="tmp-board-test")
@patch("backend.integrations.slack.lists_client.verify_list_id", return_value=(True, ""))
def test_link_board_derives_key_from_channel_name(mock_verify, mock_fetch, tmp_path):
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C_TMP",
        raw_text="@alfred link board to F0BNP40SLV9",
        cleaned_intent="link board to F0BNP40SLV9",
    )
    response = try_slack_board_admin_command(
        task, AlfredConfig(slack=SlackConfig(enabled=True, bot_token="xoxb-test")), tmp_path
    )
    assert response is not None
    text = response.payload.data.get("text") or ""
    assert "tmp-board-test" in text
    binding = db_get_board_binding_for_channel(tmp_path, "C_TMP")
    assert binding is not None
    assert binding["board_key"] == "tmp-board-test"
    workflow = db_get_channel_workflow(tmp_path, "C_TMP")
    assert workflow is not None
    assert workflow["ticket_system"] == "slack_list"
    mock_fetch.assert_called_once()
    mock_verify.assert_called_once()


@patch("backend.integrations.slack.lists_client.verify_list_id", return_value=(True, ""))
def test_link_board_rejects_placeholder_list_id(mock_verify, tmp_path):
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C_TMP",
        raw_text="@alfred link board to F0123ABCDEF",
        cleaned_intent="link board to F0123ABCDEF",
    )
    response = try_slack_board_admin_command(
        task,
        AlfredConfig(slack=SlackConfig(enabled=True, bot_token="xoxb-test")),
        tmp_path,
    )
    assert response is not None
    text = response.payload.data.get("text") or ""
    assert "placeholder" in text.lower()
    assert db_get_board_binding_for_channel(tmp_path, "C_TMP") is None
    mock_verify.assert_not_called()


@patch("backend.integrations.slack.lists_client.verify_list_id", return_value=(False, "List `F0BAD` is not accessible."))
def test_link_board_rejects_invalid_list_id(mock_verify, tmp_path):
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C_TMP",
        raw_text="@alfred link board to F0BAD",
        cleaned_intent="link board to F0BAD",
    )
    response = try_slack_board_admin_command(
        task,
        AlfredConfig(slack=SlackConfig(enabled=True, bot_token="xoxb-test")),
        tmp_path,
    )
    assert response is not None
    text = response.payload.data.get("text") or ""
    assert "not accessible" in text
    assert db_get_board_binding_for_channel(tmp_path, "C_TMP") is None


@patch("backend.integrations.slack.lists_client.verify_list_id", return_value=(True, ""))
@patch(
    "backend.routing.slack_board_admin.db_get_board_binding_for_channel",
    side_effect=[None, None],
)
def test_link_board_rejects_when_persist_fails(mock_get, mock_verify, tmp_path):
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C_TMP",
        raw_text="@alfred link board to F0BNP40SLV9",
        cleaned_intent="link board to F0BNP40SLV9",
    )
    response = try_slack_board_admin_command(
        task,
        AlfredConfig(slack=SlackConfig(enabled=True, bot_token="xoxb-test")),
        tmp_path,
    )
    assert response is not None
    text = response.payload.data.get("text") or ""
    assert "did not persist" in text


def test_unlink_board_removes_channel_binding(tmp_path):
    db_create_board_binding(
        tmp_path,
        board_key="tmp-board-test",
        list_id="F0BNP40SLV9",
        channel_id="C_TMP",
    )
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C_TMP",
        raw_text="@alfred unlink board",
        cleaned_intent="unlink board",
    )
    response = try_slack_board_admin_command(
        task, AlfredConfig(slack=SlackConfig(enabled=True)), tmp_path
    )
    assert response is not None
    text = response.payload.data.get("text") or ""
    assert "removed" in text.lower()
    assert db_get_board_binding_for_channel(tmp_path, "C_TMP") is None


def test_bare_unlink_removes_channel_binding(tmp_path):
    db_create_board_binding(
        tmp_path,
        board_key="tmp-board-test",
        list_id="F0BNP40SLV9",
        channel_id="C_TMP",
    )
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C_TMP",
        raw_text="@alfred unlink",
        cleaned_intent="unlink",
    )
    response = try_slack_board_admin_command(
        task, AlfredConfig(slack=SlackConfig(enabled=True)), tmp_path
    )
    assert response is not None
    text = response.payload.data.get("text") or ""
    assert "removed" in text.lower()
    assert db_get_board_binding_for_channel(tmp_path, "C_TMP") is None


def test_unlink_board_keeps_channel_workflow(tmp_path):
    db_create_board_binding(
        tmp_path,
        board_key="tmp-board-test",
        list_id="F0BNP40SLV9",
        channel_id="C_TMP",
    )
    db_upsert_channel_workflow(tmp_path, channel_id="C_TMP", ticket_system="slack_list")
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C_TMP",
        raw_text="@alfred delink board",
        cleaned_intent="delink board",
    )
    response = try_slack_board_admin_command(
        task, AlfredConfig(slack=SlackConfig(enabled=True)), tmp_path
    )
    assert response is not None
    workflow = db_get_channel_workflow(tmp_path, "C_TMP")
    assert workflow is not None
    assert workflow["ticket_system"] == "slack_list"


def test_link_board_preserves_existing_key_on_relink(tmp_path):
    db_create_board_binding(
        tmp_path,
        board_key="my-custom-board",
        list_id="FOLD",
        channel_id="C_TMP",
    )
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C_TMP",
        raw_text="@alfred link board to F0NEWLIST",
        cleaned_intent="link board to F0NEWLIST",
    )
    with patch("backend.routing.slack_board_admin.fetch_slack_channel_name", return_value="other-name"), patch(
        "backend.integrations.slack.lists_client.verify_list_id", return_value=(True, "")
    ):
        response = try_slack_board_admin_command(
            task, AlfredConfig(slack=SlackConfig(enabled=True)), tmp_path
        )
    assert response is not None
    binding = db_get_board_binding_for_channel(tmp_path, "C_TMP")
    assert binding is not None
    assert binding["board_key"] == "my-custom-board"
    assert binding["list_id"] == "F0NEWLIST"


def test_link_board_does_not_reset_existing_ticket_system(tmp_path):
    set_task = Task(
        source="slack",
        user_id="U1",
        channel_id="C_TMP",
        raw_text="@alfred set ticket system jira",
        cleaned_intent="set ticket system jira",
    )
    try_slack_board_admin_command(
        set_task, AlfredConfig(slack=SlackConfig(enabled=True)), tmp_path
    )
    link_task = Task(
        source="slack",
        user_id="U1",
        channel_id="C_TMP",
        raw_text="@alfred link board to F0BNP40SLV9 for my-board",
        cleaned_intent="link board to F0BNP40SLV9 for my-board",
    )
    try_slack_board_admin_command(
        link_task,
        AlfredConfig(slack=SlackConfig(enabled=True, bot_token="xoxb-test")),
        tmp_path,
    )
    workflow = db_get_channel_workflow(tmp_path, "C_TMP")
    assert workflow is not None
    assert workflow["ticket_system"] == "jira"
