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
    assert should_handle_docs_search_message(
        _event("Does any one has support docs for headless integration of checkout?"),
        bot_user_id="UBOT",
        slack_config=cfg,
        data_dir=tmp_path,
    )


def test_docs_search_poll_picks_up_channel_history(tmp_path: Path):
    from backend.integrations.slack.docs_listen import history_event, poll_docs_search_once
    from backend.routing.channel_settings import is_channel_write_or_admin_intent

    assert not is_channel_write_or_admin_intent(
        "Does any one has support docs for headless integration of checkout?"
    )
    db_create_board_binding(
        tmp_path,
        board_key="support",
        list_id="Fdocs",
        channel_id="Cdocs",
        docs_search_enabled=True,
    )
    cfg = SlackConfig(enabled=True, allowed_channels=["*"])
    captured: list[dict] = []

    class _Client:
        def conversations_history(self, **kwargs):
            return {
                "messages": [
                    {
                        "user": "U1",
                        "text": "Does any one has support docs for headless integration of checkout?",
                        "ts": "100.1",
                    }
                ]
            }

    handled = poll_docs_search_once(
        _Client(),
        slack_config=cfg,
        data_dir=tmp_path,
        bot_user_id="UBOT",
        on_event=captured.append,
        now=200.0,
    )
    assert handled == 1
    assert captured[0]["channel"] == "Cdocs"
    assert "headless" in captured[0]["text"]
    import json

    cursors = json.loads((tmp_path / "docs_search_cursors.json").read_text())
    assert "100.1" in (cursors["Cdocs"].get("seen") or [])
    handled_again = poll_docs_search_once(
        _Client(),
        slack_config=cfg,
        data_dir=tmp_path,
        bot_user_id="UBOT",
        on_event=captured.append,
        now=201.0,
    )
    assert handled_again == 0
    event = history_event("Cdocs", {"user": "U1", "text": "hello", "ts": "1"})
    assert event["channel"] == "Cdocs"


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
