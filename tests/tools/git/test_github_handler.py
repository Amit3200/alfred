"""Tests for GitHub webhook ack reactions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.integrations.github.handler import process_github_webhook_payload
from backend.models.config import AlfredConfig, GitConfig, GitHubAppConfig


def test_webhook_queues_and_reacts_eyes_immediately():
    manager = MagicMock()
    config = AlfredConfig(
        github=GitHubAppConfig(enabled=True, bot_login="alfred"),
        git=GitConfig(enabled=True, provider="github", token="ghp_test"),
    )
    manager.load_merged.return_value = (config, MagicMock())

    payload = {
        "_github_event": "issue_comment",
        "action": "created",
        "comment": {
            "id": 123,
            "body": "@alfred review this PR",
            "user": {"login": "dev", "type": "User"},
        },
        "issue": {
            "number": 7,
            "html_url": "https://github.com/AcmeCorp/platform/pull/7",
            "pull_request": {},
        },
        "repository": {"full_name": "AcmeCorp/platform"},
    }

    with (
        patch("backend.integrations.github.handler.react_to_issue_comment") as react,
        patch("backend.db.sqlite_queue.SQLiteQueue") as queue_cls,
    ):
        mock_queue = MagicMock()
        queue_cls.return_value = mock_queue
        status = process_github_webhook_payload(payload, manager=manager)

    assert status == "queued"
    react.assert_called_once()
    assert react.call_args.kwargs["content"] == "eyes"
    assert react.call_args.kwargs["comment_id"] == 123
    mock_queue.push.assert_called_once()
