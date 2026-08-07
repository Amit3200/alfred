"""Resolve Slack board/channel workflow config from SQLite (runtime, no restart)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.db.slack_workflows_db import (
    db_get_board_binding_for_channel,
    db_has_active_bindings,
    db_list_board_bindings,
)
from backend.models.config import AlfredConfig, SlackBoardColumnMap, SlackBoardProfile
from backend.models.task import Task
from backend.observability.checkpoint import current_data_dir

logger = logging.getLogger(__name__)


def resolve_data_dir(explicit: Path | None = None) -> Path | None:
    if explicit is not None:
        return explicit
    return current_data_dir.get()


def board_feature_enabled(config: AlfredConfig, data_dir: Path | None = None) -> bool:
    if not config.slack.enabled:
        return False
    data_dir = resolve_data_dir(data_dir)
    if data_dir and db_has_active_bindings(data_dir):
        return True
    boards = getattr(config.slack, "board_workflows", None)
    return bool(boards and boards.enabled and boards.boards)


def binding_to_profile(binding: dict[str, Any]) -> SlackBoardProfile:
    cols = binding.get("columns") or {}
    return SlackBoardProfile(
        name=str(binding.get("board_key") or "board"),
        list_id=str(binding.get("list_id") or ""),
        channel_ids=[str(binding.get("channel_id") or "")],
        display_id_prefix=str(binding.get("display_id_prefix") or "TS"),
        default_status=str(binding.get("default_status") or "Not picked"),
        auto_approve_writes=bool(binding.get("auto_approve_writes")),
        columns=SlackBoardColumnMap(
            title=str(cols.get("title") or "Name"),
            status=str(cols.get("status") or "Status"),
            severity=str(cols.get("severity") or "Severity"),
            assignee=str(cols.get("assignee") or "Assignee"),
            merchant=str(cols.get("merchant") or "Merchant Name"),
            merchant_domain=str(cols.get("merchant_domain") or "Merchant Domain"),
            details=str(cols.get("details") or "Ticket Details"),
            display_id=str(cols.get("display_id") or ""),
        ),
    )


def resolve_board_for_channel(
    config: AlfredConfig,
    channel_id: str,
    *,
    data_dir: Path | None = None,
) -> SlackBoardProfile | None:
    if not board_feature_enabled(config, data_dir):
        return None
    channel_id = (channel_id or "").strip()
    if not channel_id:
        return None

    data_dir = resolve_data_dir(data_dir)
    if data_dir:
        binding = db_get_board_binding_for_channel(data_dir, channel_id)
        if binding:
            return binding_to_profile(binding)

    boards = getattr(config.slack, "board_workflows", None)
    if boards and boards.enabled:
        for board in boards.boards:
            if not board.list_id:
                continue
            if not board.channel_ids or channel_id in board.channel_ids:
                return board
    return None


def resolve_board_for_task(
    config: AlfredConfig,
    task: Task,
    *,
    data_dir: Path | None = None,
) -> SlackBoardProfile | None:
    return resolve_board_for_channel(config, task.channel_id or "", data_dir=data_dir)


def resolve_board_by_key(
    config: AlfredConfig,
    board_key: str,
    *,
    channel_id: str = "",
    data_dir: Path | None = None,
) -> SlackBoardProfile | None:
    if not board_feature_enabled(config, data_dir):
        return None
    name = (board_key or "").strip().lower()
    data_dir = resolve_data_dir(data_dir)
    if data_dir and name:
        for binding in db_list_board_bindings(data_dir):
            if not binding.get("enabled"):
                continue
            if str(binding.get("board_key") or "").lower() != name:
                continue
            if channel_id and binding.get("channel_id") != channel_id:
                continue
            return binding_to_profile(binding)

    boards = getattr(config.slack, "board_workflows", None)
    if boards and boards.enabled:
        for board in boards.boards:
            if name and board.name.lower() != name:
                continue
            if channel_id and board.channel_ids and channel_id not in board.channel_ids:
                continue
            if board.list_id:
                return board
    return None


def channel_ticket_system(
    channel_id: str,
    *,
    data_dir: Path | None = None,
) -> str:
    from backend.db.slack_workflows_db import db_get_channel_workflow

    data_dir = resolve_data_dir(data_dir)
    if not data_dir or not channel_id:
        return "ask"
    row = db_get_channel_workflow(data_dir, channel_id)
    if not row or not row.get("enabled"):
        return "ask"
    return str(row.get("ticket_system") or "ask")


def channel_jira_project_key(
    channel_id: str,
    *,
    data_dir: Path | None = None,
) -> str | None:
    from backend.db.slack_workflows_db import db_get_channel_workflow

    data_dir = resolve_data_dir(data_dir)
    if not data_dir or not channel_id:
        return None
    row = db_get_channel_workflow(data_dir, channel_id)
    if not row or not row.get("enabled"):
        return None
    key = str(row.get("jira_project_key") or "").strip().upper()
    return key or None
