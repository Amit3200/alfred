"""Unmentioned Slack messages for per-channel docs search."""

from __future__ import annotations

from pathlib import Path

from backend.db.slack_workflows_db import db_create_board_binding
from backend.integrations.slack.docs_listen import should_handle_docs_search_message
from backend.models.config import SlackConfig


def _event(text: str, *, channel: str = "Cdocs", user: str = "U1", **extra) -> dict:
    payload = {
        "type": "message",
        "channel": channel,
        "user": user,
        "text": text,
        "ts": "1.0",
        "channel_type": "channel",
    }
    payload.update(extra)
    return payload


def test_docs_search_message_requires_toggle(tmp_path: Path):
    db_create_board_binding(
        tmp_path,
        board_key="support",
        list_id="Fdocs",
        channel_id="Cdocs",
        docs_search_enabled=False,
    )
    cfg = SlackConfig(enabled=True, allowed_channels=["*"])
    assert not should_handle_docs_search_message(
        _event("how does checkout work?"),
        bot_user_id="UBOT",
        slack_config=cfg,
        data_dir=tmp_path,
    )


def test_docs_search_message_handles_human_question(tmp_path: Path):
    db_create_board_binding(
        tmp_path,
        board_key="support",
        list_id="Fdocs",
        channel_id="Cdocs",
        docs_search_enabled=True,
    )
    cfg = SlackConfig(enabled=True, allowed_channels=["*"])
    assert should_handle_docs_search_message(
        _event("how does checkout work?"),
        bot_user_id="UBOT",
        slack_config=cfg,
        data_dir=tmp_path,
    )


def test_docs_search_message_skips_mentions_bots_and_writes(tmp_path: Path):
    db_create_board_binding(
        tmp_path,
        board_key="support",
        list_id="Fdocs",
        channel_id="Cdocs",
        docs_search_enabled=True,
    )
    cfg = SlackConfig(enabled=True, allowed_channels=["*"])
    kwargs = {"bot_user_id": "UBOT", "slack_config": cfg, "data_dir": tmp_path}
    assert not should_handle_docs_search_message(
        _event("how does checkout work? <@UBOT>"), **kwargs
    )
    assert not should_handle_docs_search_message(
        _event("how does checkout work?", bot_id="B123"), **kwargs
    )
    assert not should_handle_docs_search_message(_event("thanks"), **kwargs)
    assert not should_handle_docs_search_message(
        _event("create a task for payment timeout"), **kwargs
    )
    assert not should_handle_docs_search_message(
        _event("how does checkout work?", channel_type="im"), **kwargs
    )
