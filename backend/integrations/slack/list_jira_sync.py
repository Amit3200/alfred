"""Auto-create JIRA bugs from Slack List workflow messages."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from backend.db.list_jira_sync_store import ListJiraSyncStore
from backend.formatting.slack_lists import (
    extract_embedded_list_records,
    extract_list_refs,
    list_record_to_field_map,
)
from backend.integrations.jira.api import JiraApiClient
from backend.integrations.slack.sanitize import channel_allowed
from backend.models.config import AlfredConfig, SlackListJiraSyncConfig

logger = logging.getLogger(__name__)

_IGNORED_MESSAGE_SUBTYPES = frozenset(
    {
        "message_changed",
        "message_deleted",
        "channel_join",
        "channel_leave",
        "channel_topic",
        "channel_purpose",
        "channel_name",
        "channel_archive",
        "channel_unarchive",
        "group_join",
        "group_leave",
        "ekm_access_denied",
        "thread_broadcast",
        "reply_broadcast",
    }
)

_SUMMARY_FIELD_NAMES = ("Name", "Title", "name", "title")
_DESCRIPTION_SKIP = frozenset({"Name", "Title", "name", "title", "Status", "status"})


@dataclass
class ListJiraSyncResult:
    created: bool
    skipped: bool = False
    skip_reason: str = ""
    jira_key: str = ""
    jira_url: str = ""
    record_id: str = ""
    error: str = ""


def should_handle_message_event(event: dict, *, bot_user_id: str) -> bool:
    subtype = event.get("subtype")
    if subtype in _IGNORED_MESSAGE_SUBTYPES:
        return False
    if subtype not in (None, "bot_message", "file_share"):
        return False
    user = event.get("user") or ""
    if bot_user_id and user == bot_user_id:
        return False
    if event.get("hidden"):
        return False
    return bool(event.get("channel"))


def sync_channel_allowed(channel_id: str, config: AlfredConfig) -> bool:
    sync = config.slack.list_jira_sync
    watch = [entry.strip() for entry in sync.channel_ids if entry.strip()]
    if watch:
        if "*" in watch:
            return True
        return channel_id in watch
    return channel_allowed(channel_id, config.slack)


def try_sync_list_message(
    event: dict,
    config: AlfredConfig,
    *,
    data_dir: Any,
    jira_client: JiraApiClient | None = None,
) -> ListJiraSyncResult:
    sync = config.slack.list_jira_sync
    if not sync.enabled:
        return ListJiraSyncResult(created=False, skipped=True, skip_reason="disabled")

    if not config.jira.enabled:
        return ListJiraSyncResult(created=False, skipped=True, skip_reason="jira_disabled")

    channel_id = str(event.get("channel") or "")
    if not sync_channel_allowed(channel_id, config):
        return ListJiraSyncResult(created=False, skipped=True, skip_reason="channel_not_allowed")

    embedded = extract_embedded_list_records([event])
    if not embedded:
        return ListJiraSyncResult(created=False, skipped=True, skip_reason="no_list_record")

    if sync.list_id.strip() and not _message_matches_list_id(event, sync.list_id.strip()):
        return ListJiraSyncResult(created=False, skipped=True, skip_reason="list_id_mismatch")

    record_id, record, schema = embedded[0]
    fields = list_record_to_field_map(record, schema=schema)
    status = _field_value_ci(fields, "Status")
    if not _status_eligible(status, sync):
        return ListJiraSyncResult(
            created=False,
            skipped=True,
            skip_reason=f"status_not_eligible:{status or 'missing'}",
            record_id=record_id,
        )

    store = ListJiraSyncStore(data_dir)
    if store.has(record_id):
        existing = store.get(record_id) or {}
        return ListJiraSyncResult(
            created=False,
            skipped=True,
            skip_reason="already_synced",
            record_id=record_id,
            jira_key=str(existing.get("jira_key") or ""),
            jira_url=str(existing.get("jira_url") or ""),
        )

    summary = _build_summary(event, fields)
    if not summary:
        return ListJiraSyncResult(
            created=False,
            skipped=True,
            skip_reason="missing_summary",
            record_id=record_id,
        )

    priority = _map_priority(_field_value_ci(fields, "Severity"))
    description = _build_description(
        event,
        fields,
        record_id=record_id,
        list_id=sync.list_id.strip(),
        channel_id=channel_id,
    )

    try:
        client = jira_client or JiraApiClient.from_alfred_config(config)
        created = client.create_issue(
            project=sync.jira_project,
            summary=summary,
            issue_type=sync.issue_type,
            priority=priority,
            description=description,
        )
    except Exception as exc:
        logger.exception("list_jira_sync failed for record %s", record_id)
        return ListJiraSyncResult(
            created=False,
            skipped=False,
            record_id=record_id,
            error=str(exc),
        )

    jira_key = str(created.get("key") or "")
    jira_url = str(created.get("url") or "")
    thread_ts = str(event.get("thread_ts") or event.get("ts") or "")
    store.put(
        record_id,
        jira_key=jira_key,
        jira_url=jira_url,
        list_id=sync.list_id.strip(),
        channel_id=channel_id,
        thread_ts=thread_ts,
    )
    logger.info(
        "list_jira_sync created %s for slack list record %s channel=%s",
        jira_key,
        record_id,
        channel_id,
    )
    return ListJiraSyncResult(
        created=True,
        record_id=record_id,
        jira_key=jira_key,
        jira_url=jira_url,
    )


def announce_sync_result(client: Any, event: dict, result: ListJiraSyncResult, sync: SlackListJiraSyncConfig) -> None:
    if not sync.announce_in_thread:
        return
    channel_id = event.get("channel")
    thread_ts = event.get("thread_ts") or event.get("ts")
    if not channel_id or not thread_ts:
        return

    if result.created and result.jira_key:
        text = f"Created JIRA bug *{result.jira_key}* — {result.jira_url}"
    elif result.error:
        text = f"Could not create JIRA for this Slack List ticket: {result.error}"
    else:
        return

    try:
        client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=text)
    except Exception:
        logger.exception("Failed to announce list_jira_sync result in Slack")


def _message_matches_list_id(event: dict, list_id: str) -> bool:
    refs = extract_list_refs([event])
    if any(ref[0] == list_id for ref in refs):
        return True
    blob = str(event)
    return list_id in blob


def _status_eligible(status: str, sync: SlackListJiraSyncConfig) -> bool:
    allowed = [entry.strip().lower() for entry in sync.eligible_statuses if entry.strip()]
    if not allowed:
        return True
    return status.strip().lower() in allowed


def _field_value_ci(fields: dict[str, str], name: str) -> str:
    target = name.lower()
    for key, value in fields.items():
        if key.lower() == target:
            return value
    return ""


def _build_summary(event: dict, fields: dict[str, str]) -> str:
    for name in _SUMMARY_FIELD_NAMES:
        value = fields.get(name) or _field_value_ci(fields, name)
        if value.strip():
            return _truncate(value.strip(), 240)
    for attachment in event.get("attachments") or []:
        if not isinstance(attachment, dict):
            continue
        title = str(attachment.get("title") or "").strip()
        if title:
            return _truncate(title, 240)
    return ""


def _build_description(
    event: dict,
    fields: dict[str, str],
    *,
    record_id: str,
    list_id: str,
    channel_id: str,
) -> str:
    lines = ["Auto-created from Slack List (Bugs tracker).", ""]
    for label, value in fields.items():
        if label in _DESCRIPTION_SKIP or label.lower() in {name.lower() for name in _DESCRIPTION_SKIP}:
            continue
        lines.append(f"{label}: {value}")
    lines.append("")
    lines.append(f"Slack List record: {record_id}")
    if list_id:
        lines.append(f"Slack List ID: {list_id}")
    permalink = _slack_permalink(event, channel_id)
    if permalink:
        lines.append(f"Slack thread: {permalink}")
    reporter = str(event.get("text") or "").strip()
    if reporter:
        lines.append("")
        lines.append("Workflow message:")
        lines.append(reporter)
    return "\n".join(lines).strip()


def _map_priority(severity: str) -> str | None:
    normalized = severity.strip().lower()
    if not normalized:
        return None
    if "high" in normalized or "critical" in normalized or "p0" in normalized or "p1" in normalized:
        return "High"
    if "low" in normalized or "p3" in normalized:
        return "Low"
    if "medium" in normalized or "p2" in normalized:
        return "Medium"
    return severity.strip() or None


def _slack_permalink(event: dict, channel_id: str) -> str:
    ts = str(event.get("thread_ts") or event.get("ts") or "")
    if not channel_id or not ts:
        return ""
    ts_link = ts.replace(".", "")
    team = str(event.get("team") or "")
    if team:
        return f"https://app.slack.com/client/{team}/{channel_id}/thread/{channel_id}-{ts_link}"
    return ""


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
