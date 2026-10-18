"""Tests for Slack board create bootstrap."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.models.config import AlfredConfig, SlackBoardColumnMap, SlackBoardProfile, SlackBoardWorkflowsConfig, SlackConfig
from backend.models.task import Task
from backend.routing.slack_board.bootstrap import bootstrap_slack_board_create


def _board_config() -> AlfredConfig:
    return AlfredConfig(
        slack=SlackConfig(
            enabled=True,
            bot_token="xoxb-test",
            board_workflows=SlackBoardWorkflowsConfig(
                enabled=True,
                boards=[
                    SlackBoardProfile(
                        name="bugs-tracker",
                        list_id="Fbugs001",
                        channel_ids=["Ctech"],
                        columns=SlackBoardColumnMap(),
                    )
                ],
            ),
        )
    )


def test_bootstrap_create_from_thread(tmp_path: Path):
    config = _board_config()
    client = MagicMock()
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="Ctech",
        thread_ts="111.222",
        raw_text="create task for api 500 on cart for above",
        cleaned_intent="create task for api 500 on cart for above",
    )
    fake_create = {
        "record_id": "RecNEW",
        "display_id": "TS-7",
        "title": "api 500 on cart",
        "status": "Not picked",
        "board": "bugs-tracker",
    }
    with (
        patch(
            "backend.routing.slack_board.bootstrap.fetch_thread_messages",
            return_value=[{"text": "user: cart fails with 500"}],
        ),
        patch(
            "backend.routing.slack_board.bootstrap.create_board_task",
            return_value=fake_create,
        ) as create_mock,
        patch("backend.routing.slack_board.bootstrap._bot_user_id", return_value="UBOT"),
    ):
        text = bootstrap_slack_board_create(client, config, task=task, data_dir=tmp_path)
    assert "TS-7" in text
    assert "RecNEW" in text
    create_mock.assert_called_once()
    assert create_mock.call_args.kwargs["title"] == "api 500 on cart"


def test_bootstrap_disabled():
    config = AlfredConfig(slack=SlackConfig(enabled=False))
    task = Task(source="slack", user_id="", channel_id="C", raw_text="create task", cleaned_intent="create task")
    text = bootstrap_slack_board_create(MagicMock(), config, task=task, data_dir=Path("."))
    assert "disabled" in text.lower()
