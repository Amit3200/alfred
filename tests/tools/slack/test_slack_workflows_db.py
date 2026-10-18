"""Tests for SQLite Slack workflow storage."""

from __future__ import annotations

from pathlib import Path

import pytest

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

    assert db_bump_display_id(tmp_path, channel_id="Ctech", prefix="TS") == "TS-5"
    binding = db_get_board_binding_for_channel(tmp_path, "Ctech")
    assert binding["next_display_num"] == 6


def test_display_id_bump_isolated_per_channel(tmp_path: Path):
    db_create_board_binding(
        tmp_path,
        board_key="shared-key",
        list_id="F001",
        channel_id="C1",
        display_id_prefix="TS",
        next_display_num=1,
    )
    db_create_board_binding(
        tmp_path,
        board_key="shared-key",
        list_id="F002",
        channel_id="C2",
        display_id_prefix="TS",
        next_display_num=10,
    )
    assert db_bump_display_id(tmp_path, channel_id="C1", prefix="TS") == "TS-1"
    assert db_bump_display_id(tmp_path, channel_id="C2", prefix="TS") == "TS-10"
    assert db_get_board_binding_for_channel(tmp_path, "C1")["next_display_num"] == 2
    assert db_get_board_binding_for_channel(tmp_path, "C2")["next_display_num"] == 11


def test_list_id_unique_across_channels(tmp_path: Path):
    db_create_board_binding(
        tmp_path,
        board_key="board-a",
        list_id="FSHARED",
        channel_id="C1",
    )
    with pytest.raises(ValueError, match="already linked"):
        db_create_board_binding(
            tmp_path,
            board_key="board-b",
            list_id="FSHARED",
            channel_id="C2",
        )


def test_repair_board_bindings_removes_duplicate_list_rows(tmp_path: Path):
    import sqlite3

    from backend.db.slack_workflows_db import db_repair_board_bindings
    from backend.paths import db_path

    db_file = db_path(tmp_path)
    conn = sqlite3.connect(db_file)
    conn.execute(
        """
        CREATE TABLE slack_board_bindings (
            id TEXT PRIMARY KEY,
            board_key TEXT NOT NULL,
            list_id TEXT NOT NULL,
            list_name TEXT NOT NULL DEFAULT '',
            channel_id TEXT NOT NULL UNIQUE,
            channel_name TEXT NOT NULL DEFAULT '',
            display_id_prefix TEXT NOT NULL DEFAULT 'TS',
            next_display_num INTEGER NOT NULL DEFAULT 1,
            default_status TEXT NOT NULL DEFAULT 'Not picked',
            auto_approve_writes INTEGER NOT NULL DEFAULT 0,
            column_map_json TEXT NOT NULL DEFAULT '{}',
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    now = 1.0
    conn.execute(
        """
        INSERT INTO slack_board_bindings (
            id, board_key, list_id, list_name, channel_id, channel_name,
            display_id_prefix, next_display_num, default_status,
            auto_approve_writes, column_map_json, enabled, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("old", "bugs", "FSHARED", "", "C1", "", "TS", 1, "Not picked", 0, "{}", 1, now, now),
    )
    conn.execute(
        """
        INSERT INTO slack_board_bindings (
            id, board_key, list_id, list_name, channel_id, channel_name,
            display_id_prefix, next_display_num, default_status,
            auto_approve_writes, column_map_json, enabled, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("new", "bugs", "FSHARED", "", "C2", "", "TS", 1, "Not picked", 0, "{}", 1, now + 1, now + 1),
    )
    conn.commit()
    conn.close()

    removed = db_repair_board_bindings(tmp_path)
    assert removed == 1
    rows = db_get_board_binding_for_channel(tmp_path, "C1"), db_get_board_binding_for_channel(
        tmp_path, "C2"
    )
    active = [row for row in rows if row is not None]
    assert len(active) == 1
    assert active[0]["list_id"] == "FSHARED"


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


def test_board_binding_persona_and_docs_search(tmp_path: Path):
    from backend.db.slack_workflows_db import db_update_board_binding

    binding = db_create_board_binding(
        tmp_path,
        board_key="support",
        list_id="Fdocs",
        channel_id="Cdocs",
        persona_prompt="You are billing support. Prefer invoice docs.",
        docs_search_enabled=True,
    )
    assert binding["persona_prompt"] == "You are billing support. Prefer invoice docs."
    assert binding["docs_search_enabled"] is True

    updated = db_update_board_binding(
        tmp_path,
        binding["id"],
        persona_prompt="Prefer settlement docs.",
        docs_search_enabled=False,
    )
    assert updated is not None
    assert updated["persona_prompt"] == "Prefer settlement docs."
    assert updated["docs_search_enabled"] is False
    loaded = db_get_board_binding_for_channel(tmp_path, "Cdocs")
    assert loaded is not None
    assert loaded["persona_prompt"] == "Prefer settlement docs."
