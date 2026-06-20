"""Tests for Slack runner health status shape."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.models.config import default_config
from backend.slack.listener import SlackSocketRunner


def test_status_ok_when_running():
    runner = SlackSocketRunner(MagicMock())
    runner.running = True
    config = default_config()
    config.slack.enabled = True
    config.slack.bot_token = "xoxb-test"
    config.slack.app_token = "xapp-test"
    config.slack.signing_secret = "secret"
    runner.manager.load_merged.return_value = (config, MagicMock())

    status = runner.status()
    assert status["ok"] is True
    assert "Listening" in status["message"]


def test_status_fail_when_ready_but_not_running():
    runner = SlackSocketRunner(MagicMock())
    runner.running = False
    config = default_config()
    config.slack.enabled = True
    config.slack.bot_token = "xoxb-test"
    config.slack.app_token = "xapp-test"
    config.slack.signing_secret = "secret"
    runner.manager.load_merged.return_value = (config, MagicMock())

    status = runner.status()
    assert status["ok"] is False
    assert status["message"]
