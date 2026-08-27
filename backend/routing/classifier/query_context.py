"""Per-turn query metadata for hierarchical routing (channel, board, entities)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.models.config import AlfredConfig
from backend.models.task import Task
from backend.routing.entity_extractor import EntityBag


@dataclass(frozen=True)
class QueryMetadata:
    source: str
    channel_id: str
    thread_ts: str
    user_id: str
    slack_board_linked: bool
    slack_board_name: str
    slack_board_list_id: str
    jira_enabled: bool
    jira_default_project: str
    last_intent_class: str
    last_target_system: str
    ticket_create_target: str
    channel_prefers_jira: bool = False
    channel_jira_project: str = ""
    entities: dict[str, Any] = field(default_factory=dict)

    def prompt_block(self) -> str:
        board = "none"
        if self.slack_board_linked:
            board = (
                f"linked name={self.slack_board_name or '?'} "
                f"list_id={self.slack_board_list_id or '?'}"
            )
        keys = self.entities.get("issue_keys") or []
        return "\n".join(
            [
                f"source: {self.source}",
                f"channel_id: {self.channel_id or '(none)'}",
                f"thread_ts: {self.thread_ts or '(none)'}",
                f"slack_list_board: {board}",
                f"jira_enabled: {str(self.jira_enabled).lower()}",
                f"jira_default_project: {self.jira_default_project or '(none)'}",
                f"entities.issue_keys: {keys or '[]'}",
                f"session.last_intent_class: {self.last_intent_class or '(none)'}",
                f"session.last_target_system: {self.last_target_system or '(none)'}",
                f"session.ticket_create_target: {self.ticket_create_target or '(none)'}",
                f"channel_prefers_jira_creates: {str(self.channel_prefers_jira).lower()}",
                f"channel_jira_project_key: {self.channel_jira_project or '(none)'}",
            ]
        )


def gather_query_metadata(
    task: Task,
    *,
    config: AlfredConfig,
    session: Any | None = None,
    entities: EntityBag | None = None,
    data_dir: Path | None = None,
) -> QueryMetadata:
    session_meta = dict(getattr(session, "metadata", None) or {}) if session is not None else {}
    turn = dict(session_meta.get("turn_plan") or {})
    board_name = ""
    board_list_id = ""
    board_linked = False
    path = data_dir or getattr(config, "data_dir", None)
    if task.source == "slack" and (task.channel_id or "").strip() and config.slack.enabled:
        try:
            from backend.domains.slack_board.operations import board_enabled, resolve_board_for_task

            if board_enabled(config, path):
                board = resolve_board_for_task(config, task, data_dir=path)
                if board is not None:
                    board_linked = True
                    board_name = str(getattr(board, "name", "") or "")
                    board_list_id = str(getattr(board, "list_id", "") or "")
        except Exception:
            board_linked = False

    entity_payload: dict[str, Any] = {}
    if entities is not None:
        entity_payload = {
            "issue_keys": list(entities.issue_keys),
            "spreadsheet_ids": list(entities.spreadsheet_ids),
            "document_ids": list(entities.document_ids),
        }

    prefers_jira = False
    jira_project = ""
    if task.source == "slack" and (task.channel_id or "").strip():
        try:
            from backend.integrations.slack.workflow_registry import channel_jira_project_key
            from backend.routing.create_target_precedence import channel_prefers_jira_creates

            prefers_jira = channel_prefers_jira_creates(
                channel_id=task.channel_id or "",
                data_dir=path,
                session_metadata=session_meta,
            )
            jira_project = str(
                channel_jira_project_key(task.channel_id or "", data_dir=path) or ""
            )
        except Exception:
            prefers_jira = False

    return QueryMetadata(
        source=str(task.source or ""),
        channel_id=str(task.channel_id or ""),
        thread_ts=str(task.thread_ts or ""),
        user_id=str(task.user_id or ""),
        slack_board_linked=board_linked,
        slack_board_name=board_name,
        slack_board_list_id=board_list_id,
        jira_enabled=bool(config.jira.enabled),
        jira_default_project=str(config.jira.default_project or ""),
        last_intent_class=str(turn.get("intent_class") or ""),
        last_target_system=str(turn.get("target_system") or ""),
        ticket_create_target=str(session_meta.get("ticket_create_target") or ""),
        channel_prefers_jira=prefers_jira,
        channel_jira_project=jira_project,
        entities=entity_payload,
    )
