"""Tests for Slack user name resolution."""

from unittest.mock import MagicMock

from backend.ingress.slack_users import (
    SlackUserResolver,
    format_user_list,
    pick_slack_display_name,
)


def test_pick_slack_display_name_prefers_display_name():
    user = {
        "id": "U1",
        "name": "alex",
        "real_name": "Alex Example",
        "profile": {"display_name": "Alex", "real_name": "Alex Example"},
    }
    assert pick_slack_display_name(user) == "Alex"


def test_format_user_list_uses_resolved_names():
    assert format_user_list(["U1", "U2"], {"U1": "Alex", "U2": "Sam"}) == "Alex, Sam"


def test_slack_user_resolver_caches_users_info():
    client = MagicMock()
    client.users_info.return_value = {
        "ok": True,
        "user": {
            "id": "U07EE3LAS84",
            "name": "alex",
            "real_name": "Alex Example",
            "profile": {"display_name": "Alex"},
        },
    }
    resolver = SlackUserResolver(client)
    assert resolver.display_name("U07EE3LAS84") == "Alex"
    client.users_info.assert_called_once()
