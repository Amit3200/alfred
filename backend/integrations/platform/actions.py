"""Apply normalized connector entities onto Slack Lists and JIRA."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.integrations.platform.store import ConnectorSyncStore
from backend.integrations.platform.types import ExternalEntity, ReplicaTarget
from backend.models.config import AlfredConfig

logger = logging.getLogger(__name__)


def _entity_description(entity: ExternalEntity) -> str:
    lines = [
        f"Summary: {entity.title}",
        f"{entity.connector_id} {entity.kind}: `{entity.external_id}`",
    ]
    if entity.chat_name or entity.chat_id:
        lines.append(f"WhatsApp chat: {entity.chat_name or entity.chat_id}")
    if entity.assignee_hint:
        lines.append(f"Assignee: {entity.assignee_hint}")
    if entity.status:
        lines.append(f"Status: {entity.status}")
    if entity.labels:
        lines.append(f"Labels: {', '.join(entity.labels)}")
    if entity.description:
        lines.extend(["", entity.description.strip()])
    return "\n".join(lines)[:8000]


def _resolve_board(config: AlfredConfig, data_dir: Path, board_key: str = ""):
    from backend.db.slack_workflows_db import db_list_board_bindings
    from backend.domains.slack_board.operations import resolve_board_any_channel
    from backend.integrations.slack.workflow_registry import binding_to_profile

    if board_key:
        board = resolve_board_any_channel(config, board_name=board_key, data_dir=data_dir)
        if board is not None:
            return board
    for binding in db_list_board_bindings(data_dir):
        if binding.get("enabled"):
            return binding_to_profile(binding)
    return None


def _create_slack_board_item(
    config: AlfredConfig,
    data_dir: Path,
    entity: ExternalEntity,
) -> dict[str, Any]:
    from slack_sdk import WebClient

    from backend.db.slack_board_store import SlackBoardStore
    from backend.domains.slack_board.operations import create_board_task

    settings = getattr(getattr(config, "connectors", None), entity.connector_id, None)
    board_key = str(getattr(settings, "slack_board_key", "") or "")
    board = _resolve_board(config, data_dir, board_key)
    if board is None:
        raise RuntimeError("No Slack List board is linked. Run `@alfred setup board` first.")
    token = (config.slack.bot_token or "").strip()
    if not token:
        raise RuntimeError("Slack bot token is not configured.")
    client = WebClient(token=token)
    store = SlackBoardStore(data_dir)
    channel_id = ""
    if board.channel_ids:
        channel_id = str(board.channel_ids[0])
    result = create_board_task(
        client,
        config,
        store,
        board,
        title=entity.title[:200],
        description=_entity_description(entity),
        severity=entity.priority,
        channel_id=channel_id,
    )
    return {
        "record_id": result.get("record_id") or "",
        "display_id": result.get("display_id") or "",
        "list_id": result.get("list_id") or board.list_id,
        "channel_id": channel_id,
        "open_url": result.get("open_url") or "",
    }


def _create_jira_issue(
    config: AlfredConfig,
    entity: ExternalEntity,
) -> dict[str, Any]:
    from backend.integrations.jira.api import JiraApiClient

    settings = getattr(getattr(config, "connectors", None), entity.connector_id, None)
    project = str(getattr(settings, "jira_project", "") or config.jira.default_project or "").strip()
    if not project:
        raise RuntimeError("No JIRA project configured for this connector.")
    issue_types = getattr(config.jira, "project_issue_types", None) or {}
    issue_type = str(issue_types.get(project) or "Task")
    client = JiraApiClient.from_alfred_config(config)
    created = client.create_issue(
        project=project,
        summary=entity.title[:200],
        issue_type=issue_type,
        priority=entity.priority if entity.priority in {"High", "Medium", "Low"} else None,
        description=_entity_description(entity),
        assignee=entity.assignee_hint or None,
    )
    return {
        "jira_key": created.get("key") or "",
        "jira_url": created.get("url") or "",
    }


def apply_entity(
    entity: ExternalEntity,
    config: AlfredConfig,
    *,
    data_dir: Path,
    targets: tuple[ReplicaTarget, ...] = (),
) -> dict[str, Any]:
    """Create or reuse Slack List / JIRA items for a connector entity."""
    if entity.action == "ignore" or not entity.external_id or not entity.title.strip():
        return {"ok": True, "status": "ignored", "key": entity.mapping_key()}

    store = ConnectorSyncStore(data_dir)
    mapping = store.get(entity.mapping_key()) or {}
    if entity.action == "close" and not mapping:
        return {"ok": True, "status": "ignored_close", "key": entity.mapping_key()}
    results: dict[str, Any] = {"ok": True, "key": entity.mapping_key(), "targets": {}}

    for target in targets:
        try:
            if target == "slack_board":
                if mapping.get("slack_record_id"):
                    results["targets"]["slack_board"] = {
                        "status": "exists",
                        "record_id": mapping.get("slack_record_id"),
                        "display_id": mapping.get("slack_display_id"),
                    }
                    continue
                created = _create_slack_board_item(config, data_dir, entity)
                mapping.update(
                    {
                        "slack_record_id": created.get("record_id"),
                        "slack_display_id": created.get("display_id"),
                        "slack_list_id": created.get("list_id"),
                        "slack_channel_id": created.get("channel_id"),
                    }
                )
                results["targets"]["slack_board"] = {"status": "created", **created}
            elif target == "jira":
                if mapping.get("jira_key"):
                    results["targets"]["jira"] = {
                        "status": "exists",
                        "jira_key": mapping.get("jira_key"),
                        "jira_url": mapping.get("jira_url"),
                    }
                    continue
                created = _create_jira_issue(config, entity)
                mapping.update(created)
                results["targets"]["jira"] = {"status": "created", **created}
        except Exception as exc:
            logger.warning(
                "Connector replica failed connector=%s entity=%s target=%s: %s",
                entity.connector_id,
                entity.external_id,
                target,
                exc,
            )
            results["ok"] = False
            results["targets"][target] = {"status": "error", "error": str(exc)}

    if mapping:
        store.put(
            entity.mapping_key(),
            {
                **mapping,
                "title": entity.title,
                "kind": entity.kind,
                "connector_id": entity.connector_id,
            },
        )
    return results
