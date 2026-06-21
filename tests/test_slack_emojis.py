"""Tests for Slack workspace emoji listing."""

from __future__ import annotations

from unittest.mock import MagicMock

from backend.slack.emojis import (
    example_loading_line,
    fetch_workspace_emojis,
    filter_workspace_emojis,
    format_emojis_yaml,
)


def test_fetch_workspace_emojis_missing_scope():
    client = MagicMock()
    client.emoji_list.return_value = {
        "ok": False,
        "error": "missing_scope",
        "needed": "emoji:read",
    }

    try:
        fetch_workspace_emojis(client)
    except RuntimeError as exc:
        assert "emoji:read" in str(exc)
        assert "Reinstall to Workspace" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_fetch_workspace_emojis_splits_custom_and_alias():
    client = MagicMock()
    client.emoji_list.return_value = {
        "ok": True,
        "emoji": {
            "this_is_fine": "https://emoji.slack-edge.com/T1/this_is_fine/abc.png",
            "rollsafe": "https://emoji.slack-edge.com/T1/rollsafe/def.png",
            "fine_alias": "alias:this_is_fine",
            "smile": "alias:slightly_smiling_face",
        },
    }

    emojis = fetch_workspace_emojis(client)
    by_name = {item.name: item for item in emojis}

    assert by_name["this_is_fine"].kind == "custom"
    assert by_name["this_is_fine"].shortcode == ":this_is_fine:"
    assert by_name["fine_alias"].kind == "alias"
    assert by_name["fine_alias"].target == "this_is_fine"


def test_filter_workspace_emojis_search_and_aliases():
    from backend.slack.emojis import WorkspaceEmoji

    emojis = [
        WorkspaceEmoji(name="this_is_fine", kind="custom"),
        WorkspaceEmoji(name="sad_cat", kind="custom"),
        WorkspaceEmoji(name="fine_alias", kind="alias", target="this_is_fine"),
    ]

    assert [item.name for item in filter_workspace_emojis(emojis, search="cat")] == ["sad_cat"]
    with_aliases = {item.name for item in filter_workspace_emojis(emojis, include_aliases=True)}
    assert with_aliases == {"fine_alias", "sad_cat", "this_is_fine"}


def test_format_emojis_yaml():
    from backend.slack.emojis import WorkspaceEmoji

    emojis = [WorkspaceEmoji(name="this_is_fine", kind="custom")]
    yaml_text = format_emojis_yaml(emojis)
    assert yaml_text.startswith("loading_messages:")
    assert example_loading_line("this_is_fine") in yaml_text
