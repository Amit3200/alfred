"""Slack List resolution shims and HTTP field helpers.

CRUD verbs live in ``backend.domains.slack_board``. This module stays HTTP-adjacent
(workflow lookup + List field payloads) so integrations never import domains.
"""

from __future__ import annotations

from pathlib import Path

from backend.integrations.slack.list_fields import (  # noqa: F401
    _field_payload,
    _resolve_title_column,
    field_payload,
    load_schema,
    resolve_title_column,
)
from backend.integrations.slack.workflow_registry import (
    board_feature_enabled,
    resolve_board_by_key,
    resolve_board_for_channel,
    resolve_board_for_task as _resolve_board_for_task,
)
from backend.models.config import AlfredConfig, SlackBoardProfile
from backend.models.task import Task


def board_enabled(config: AlfredConfig, data_dir: Path | None = None) -> bool:
    return board_feature_enabled(config, data_dir)


def resolve_board_for_task(
    config: AlfredConfig,
    task: Task,
    *,
    data_dir: Path | None = None,
) -> SlackBoardProfile | None:
    return _resolve_board_for_task(config, task, data_dir=data_dir)


def resolve_board_any_channel(
    config: AlfredConfig,
    *,
    channel_id: str = "",
    board_name: str = "",
    data_dir: Path | None = None,
) -> SlackBoardProfile | None:
    if board_name:
        return resolve_board_by_key(
            config,
            board_name,
            channel_id=channel_id,
            data_dir=data_dir,
        )
    if channel_id:
        return resolve_board_for_channel(config, channel_id, data_dir=data_dir)
    return None
