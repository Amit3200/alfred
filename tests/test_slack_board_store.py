"""Tests for Slack board registry store."""

from __future__ import annotations

from pathlib import Path

from backend.db.slack_board_store import SlackBoardStore


def test_display_id_and_resolve(tmp_path: Path):
    store = SlackBoardStore(tmp_path)
    display_id = store.next_display_id("bugs", prefix="TS")
    assert display_id == "TS-1"
    store.register_record(
        "RecABC123",
        board_key="bugs",
        list_id="F001",
        channel_id="C001",
        display_id=display_id,
        thread_ts="1234.5678",
        title="Checkout timeout",
    )
    meta = store.find_record("TS-1")
    assert meta is not None
    assert meta["title"] == "Checkout timeout"
    resolved = store.resolve_record("TS-1")
    assert resolved is not None
    record_id, row = resolved
    assert record_id == "RecABC123"
    assert row["list_id"] == "F001"


def test_next_display_id_increments(tmp_path: Path):
    store = SlackBoardStore(tmp_path)
    assert store.next_display_id("bugs", prefix="TS") == "TS-1"
    assert store.next_display_id("bugs", prefix="TS") == "TS-2"
