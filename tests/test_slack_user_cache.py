"""Tests for Slack user name cache."""

from __future__ import annotations

from backend.db.slack_user_cache import SlackUserCache


def test_slack_user_cache_remembers_and_loads(tmp_path):
    cache = SlackUserCache(tmp_path)
    cache.remember("U0522NX5GG0", "Amit")
    assert cache.get("U0522NX5GG0") == "Amit"
    assert cache.get_many()["U0522NX5GG0"] == "Amit"

    reloaded = SlackUserCache(tmp_path)
    assert reloaded.get("U0522NX5GG0") == "Amit"
