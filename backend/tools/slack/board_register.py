"""Slack List board write tools."""

from __future__ import annotations

from pathlib import Path

from backend.domains.slack_board.operations import board_enabled
from backend.models.config import AlfredConfig
from backend.models.task import Task
from backend.tools.registry import ToolRegistry
from backend.tools.slack.board_tools import SlackBoardToolBundle


def register_slack_board_tools(
    registry: ToolRegistry,
    config: AlfredConfig,
    *,
    data_dir: Path | None = None,
    default_task: Task | None = None,
) -> None:
    if not board_enabled(config, data_dir):
        return
    token = (config.slack.bot_token or "").strip()
    if not token:
        return
    registry.alfred_config = config
    if data_dir is not None:
        registry.data_dir = data_dir
    extra = {"default_task": default_task} if default_task is not None else None
    SlackBoardToolBundle().register(registry, extra=extra)
