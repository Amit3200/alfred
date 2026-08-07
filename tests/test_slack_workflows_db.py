"""Tests for SQLite Slack workflow storage."""

from __future__ import annotations

from pathlib import Path

from backend.db.slack_workflows_db import (
    db_bump_display_id,
    db_create_board_binding,
    db_get_board_binding_for_channel,
    db_has_active_bindings,
    db_upsert_channel_workflow,
)
from backend.integrations.slack.workflow_registry import (
    binding_to_profile,
    channel_jira_project_key,
    channel_ticket_system,
    resolve_board_for_channel,
)
from backend.models.config import AlfredConfig, SlackConfig


def test_board_binding_and_display_id_bump(tmp_path: Path):
    db_create_board_binding(
        tmp_path,
        board_key="bugs",
        list_id="F001",
        channel_id="Ctech",
        display_id_prefix="TS",
        next_display_num=5,
    )
    assert db_has_active_bindings(tmp_path)
    binding = db_get_board_binding_for_channel(tmp_path, "Ctech")
    assert binding is not None
    assert binding["board_key"] == "bugs"

    assert db_bump_display_id(tmp_path, "bugs", prefix="TS") == "TS-5"
    binding = db_get_board_binding_for_channel(tmp_path, "Ctech")
    assert binding["next_display_num"] == 6


def test_resolve_board_from_db(tmp_path: Path):
    db_create_board_binding(
        tmp_path,
        board_key="bugs-tracker",
        list_id="Fbugs",
        channel_id="C001",
    )
    config = AlfredConfig(slack=SlackConfig(enabled=True))
    profile = resolve_board_for_channel(config, "C001", data_dir=tmp_path)
    assert profile is not None
    assert profile.list_id == "Fbugs"
    assert profile.name == "bugs-tracker"


def test_channel_workflow_policy(tmp_path: Path):
    db_upsert_channel_workflow(
        tmp_path,
        channel_id="C001",
        ticket_system="jira",
        jira_project_key="ts",
    )
    assert channel_ticket_system("C001", data_dir=tmp_path) == "jira"
    assert channel_jira_project_key("C001", data_dir=tmp_path) == "TS"

    binding = db_create_board_binding(
        tmp_path,
        board_key="bugs",
        list_id="F1",
        channel_id="C001",
    )
    profile = binding_to_profile(binding)
    assert profile.columns.title == "Name"
