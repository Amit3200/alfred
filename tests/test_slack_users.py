"""Tests for Slack user name resolution."""

from unittest.mock import MagicMock

from backend.formatting.slack_messages import format_slack_message
from backend.integrations.slack.users import (
    SlackUserResolver,
    collect_message_user_ids,
    format_user_list,
    pick_slack_display_name,
    resolve_user_ids_in_text,
    substitute_slack_user_ids,
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


def test_collect_message_user_ids_includes_authors_and_reactions():
    messages = [
        {"user": "U1", "reactions": [{"users": ["U2"]}]},
        {"user": "U3"},
    ]
    assert collect_message_user_ids(messages) == {"U1", "U2", "U3"}


def test_substitute_slack_user_ids_replaces_bare_ids_and_mentions():
    text = "U0A5JAB4R2T was unavailable. Follow up with <@U0B2Z0S0THQ>."
    result = substitute_slack_user_ids(
        text,
        {"U0A5JAB4R2T": "Alex", "U0B2Z0S0THQ": "Sam"},
    )
    assert result == "Alex was unavailable. Follow up with Sam."


def test_resolve_user_ids_in_text_uses_users_info():
    client = MagicMock()
    client.users_info.return_value = {
        "ok": True,
        "user": {
            "id": "U0A5JAB4R2T",
            "profile": {"display_name": "Azeem Hussain"},
        },
    }
    resolver = SlackUserResolver(client)
    text = resolve_user_ids_in_text("Report for U0A5JAB4R2T", resolver)
    assert text == "Report for Azeem Hussain"


def test_format_slack_message_uses_author_display_name():
    message = {"user": "U1", "ts": "1710000000.000001", "text": "Out today"}
    line = format_slack_message(message, user_names={"U1": "Alex"})
    assert "Alex:" in line
    assert "U1:" not in line


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
