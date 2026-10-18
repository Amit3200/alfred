"""Apply normalized connector entities onto Slack Lists and JIRA."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.integrations.platform.store import ConnectorSyncStore
from backend.integrations.platform.types import ExternalEntity, ReplicaTarget
from backend.models.config import AlfredConfig, SlackBoardProfile

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)


def _entity_description(entity: ExternalEntity) -> str:
    from backend.integrations.periskope.copy import list_item_details

    if entity.connector_id == "periskope":
        return list_item_details(entity, entity.extra.get("recent_messages") or [])
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


def connector_slack_channel_id(settings: Any) -> str:
    if settings is None:
        return ""
    return str(
        getattr(settings, "slack_channel_id", "")
        or getattr(settings, "summary_channel_id", "")
        or ""
    ).strip()


def resolve_connector_board(
    config: AlfredConfig,
    data_dir: Path,
    settings: Any,
) -> tuple[SlackBoardProfile | None, str]:
    """Resolve the Slack List from the connector's configured channel."""
    from backend.domains.slack_board.operations import resolve_board_any_channel
    from backend.integrations.slack.workflow_registry import resolve_board_for_channel

    channel_id = connector_slack_channel_id(settings)
    board_key = str(getattr(settings, "slack_board_key", "") or "").strip() if settings else ""
    if not channel_id:
        return None, ""
    board = resolve_board_for_channel(config, channel_id, data_dir=data_dir)
    if board is None and board_key:
        board = resolve_board_any_channel(
            config,
            board_name=board_key,
            channel_id=channel_id,
            data_dir=data_dir,
        )
    return board, channel_id


def _create_slack_board_item(
    config: AlfredConfig,
    data_dir: Path,
    entity: ExternalEntity,
) -> dict[str, Any]:
    from slack_sdk import WebClient

    from backend.db.slack_board_store import SlackBoardStore
    from backend.domains.slack_board.operations import create_board_task
    from backend.integrations.periskope.copy import group_label

    settings = getattr(getattr(config, "connectors", None), entity.connector_id, None)
    board, channel_id = resolve_connector_board(config, data_dir, settings)
    if not channel_id:
        raise RuntimeError(
            "No Slack channel is configured for this connector. "
            "Set Slack channel in Integrations → Periskope so List items and tasks land there."
        )
    if board is None:
        raise RuntimeError(
            f"No Slack List is linked to channel `{channel_id}`. "
            "Bind a board for that channel under Slack boards."
        )
    token = (config.slack.bot_token or "").strip()
    if not token:
        raise RuntimeError("Slack bot token is not configured.")
    client = WebClient(token=token)
    store = SlackBoardStore(data_dir)
    result = create_board_task(
        client,
        config,
        store,
        board,
        title=entity.title[:200],
        description=_entity_description(entity),
        severity=entity.priority,
        merchant=group_label(entity),
        channel_id=channel_id,
    )
    open_url = ""
    try:
        from backend.integrations.slack.lists_client import list_open_url

        base = list_open_url(client, result.get("list_id") or board.list_id)
        record_id = str(result.get("record_id") or "")
        if base and record_id:
            sep = "&" if "?" in base else "?"
            open_url = f"{base}{sep}record_id={record_id}"
        else:
            open_url = base
    except Exception:
        logger.debug("Could not build Slack List URL for connector replica", exc_info=True)
    return {
        "record_id": result.get("record_id") or "",
        "display_id": result.get("display_id") or "",
        "list_id": result.get("list_id") or board.list_id,
        "channel_id": channel_id,
        "open_url": open_url or result.get("url_hint") or "",
        "board_name": board.name,
        "status": board.default_status or "Not picked",
    }


def _create_jira_issue(
    config: AlfredConfig,
    entity: ExternalEntity,
    *,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    from backend.integrations.jira.api import JiraApiClient
    from backend.integrations.slack.workflow_registry import channel_jira_project_key

    settings = getattr(getattr(config, "connectors", None), entity.connector_id, None)
    project = str(getattr(settings, "jira_project", "") or "").strip()
    if not project:
        channel_id = connector_slack_channel_id(settings)
        if channel_id:
            project = str(channel_jira_project_key(channel_id, data_dir=data_dir) or "").strip()
    if not project:
        project = str(config.jira.default_project or "").strip()
    if not project:
        raise RuntimeError(
            "No JIRA project configured for this connector. "
            "Set JIRA project in Integrations → Periskope, or on the Slack channel workflow."
        )
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


def _announce_replica(
    config: AlfredConfig,
    data_dir: Path,
    entity: ExternalEntity,
    results: dict[str, Any],
) -> None:
    settings = getattr(getattr(config, "connectors", None), entity.connector_id, None)
    slack = results.get("targets", {}).get("slack_board") or {}
    jira = results.get("targets", {}).get("jira") or {}
    created = slack.get("status") == "created" or jira.get("status") == "created"
    if not created:
        return
    channel_id = str(slack.get("channel_id") or connector_slack_channel_id(settings) or "").strip()
    if not channel_id:
        return
    token = (config.slack.bot_token or "").strip()
    if not token:
        return
    from slack_sdk import WebClient

    from backend.db.slack_board_store import SlackBoardStore
    from backend.integrations.periskope.copy import announce_blocks, announce_color, announce_fallback

    display = str(slack.get("display_id") or slack.get("record_id") or "").strip()
    jira_key = str(jira.get("jira_key") or "").strip()
    list_url = str(slack.get("open_url") or "").strip()
    board_name = str(slack.get("board_name") or "").strip()
    status = str(slack.get("status") or "Not picked").strip() or "Not picked"
    text = announce_fallback(entity, display_id=display)
    blocks = announce_blocks(
        entity,
        display_id=display,
        list_url=list_url,
        jira_key=jira_key,
        board_name=board_name,
        status=status,
    )
    try:
        client = WebClient(token=token)
        response = client.chat_postMessage(
            channel=channel_id,
            text=text,
            attachments=[
                {
                    "color": announce_color(entity.priority),
                    "blocks": blocks,
                }
            ],
            unfurl_links=False,
            unfurl_media=False,
        )
        thread_ts = str(response.get("ts") or "")
        record_id = str(slack.get("record_id") or "")
        if record_id and thread_ts:
            store = SlackBoardStore(data_dir)
            meta = store.find_record(record_id) or {}
            store.register_record(
                record_id,
                board_key=str(meta.get("board_key") or ""),
                list_id=str(meta.get("list_id") or slack.get("list_id") or ""),
                channel_id=channel_id,
                display_id=str(meta.get("display_id") or slack.get("display_id") or ""),
                thread_ts=thread_ts,
                title=str(meta.get("title") or entity.title),
            )
    except Exception:
        logger.exception(
            "Failed to announce connector replica in Slack channel=%s entity=%s",
            channel_id,
            entity.external_id,
        )


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
    from backend.integrations.periskope.summarize import looks_like_ticket_id

    if entity.connector_id == "periskope" and entity.kind == "ticket" and not looks_like_ticket_id(
        entity.external_id
    ):
        logger.info(
            "Skipping connector replica with invalid ticket id connector=%s id=%r",
            entity.connector_id,
            entity.external_id[:80],
        )
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
                created = _create_jira_issue(config, entity, data_dir=data_dir)
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

    _announce_replica(config, data_dir, entity, results)

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
