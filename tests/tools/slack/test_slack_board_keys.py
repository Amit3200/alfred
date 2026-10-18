"""Tests for per-channel board key helpers."""

from __future__ import annotations

from backend.integrations.slack.board_keys import derive_board_key


def test_derive_board_key_prefers_channel_name():
    assert derive_board_key(channel_name="#eng-bugs", channel_id="C123") == "eng-bugs"


def test_derive_board_key_falls_back_to_channel_id():
    assert derive_board_key(channel_id="C0BNNSMGG91").startswith("board-")
