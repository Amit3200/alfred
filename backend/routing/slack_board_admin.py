"""In-Slack admin commands for board/channel workflow configuration (writes to DB)."""

from __future__ import annotations

import re

from backend.db.slack_workflows_db import (
    db_create_board_binding,
    db_get_board_binding_for_channel,
    db_update_board_binding,
    db_upsert_channel_workflow,
)
from backend.models.config import AlfredConfig
from backend.models.response import AssistantResponse
from backend.models.task import Task

_LINK_BOARD_RE = re.compile(
    r"\b(?:link|bind|connect)\b.{0,20}\b(?:board|list|channel)\b.{0,40}\b(?:to\s+)?(F[A-Za-z0-9]+)\b",
    re.I,
)
_SET_PREFIX_RE = re.compile(
    r"\b(?:set|change|update)\b.{0,20}\b(?:display\s*)?(?:id\s*)?prefix\b.{0,10}\b([A-Z]{1,8})\b",
    re.I,
)
_SHOW_CONFIG_RE = re.compile(
    r"\b(?:show|get|what\s+is)\b.{0,20}\b(?:board|channel)\b.{0,20}\b(?:config|setup|binding)\b",
    re.I,
)
_SET_TICKET_SYSTEM_RE = re.compile(
    r"\bset\b.{0,20}\bticket\s+system\b.{0,10}\b(slack(?:\s+list)?|jira|ask)\b",
    re.I,
)


def try_slack_board_admin_command(
    task: Task,
    config: AlfredConfig,
    data_dir,
) -> AssistantResponse | None:
    if task.source != "slack" or not config.slack.enabled:
        return None
    if not task.channel_id:
        return None

    text = task.cleaned_intent or task.raw_text or ""
    channel_id = task.channel_id

    match = _SET_TICKET_SYSTEM_RE.search(text)
    if match:
        raw = match.group(1).lower().replace(" ", "_")
        system = "slack_list" if raw.startswith("slack") else raw
        if system not in ("slack_list", "jira", "ask"):
            return AssistantResponse.from_text("Use: `@alfred set ticket system slack|jira|ask`")
        row = db_upsert_channel_workflow(
            data_dir,
            channel_id=channel_id,
            ticket_system=system,  # type: ignore[arg-type]
        )
        return AssistantResponse.from_text(
            f"Channel ticket system set to **{row['ticket_system']}** (saved — no restart needed)."
        )

    match = _LINK_BOARD_RE.search(text)
    if match:
        list_id = match.group(1)
        board_key = "bugs-tracker"
        name_match = re.search(r"\bfor\s+([a-z0-9_-]{2,40})\b", text, re.I)
        if name_match:
            board_key = name_match.group(1).lower()
        existing = db_get_board_binding_for_channel(data_dir, channel_id)
        if existing:
            updated = db_update_board_binding(
                data_dir,
                existing["id"],
                board_key=board_key,
                list_id=list_id,
            )
            binding = updated or existing
        else:
            binding = db_create_board_binding(
                data_dir,
                board_key=board_key,
                list_id=list_id,
                channel_id=channel_id,
            )
        db_upsert_channel_workflow(
            data_dir,
            channel_id=channel_id,
            ticket_system="ask",
        )
        return AssistantResponse.from_text(
            "Linked this channel to Slack List "
            f"`{binding['list_id']}` as board **{binding['board_key']}**. "
            f"Display prefix `{binding['display_id_prefix']}`, next id `{binding['display_id_prefix']}-{binding['next_display_num']}`. "
            "Edit details in **Settings → Slack boards**."
        )

    match = _SET_PREFIX_RE.search(text)
    if match:
        prefix = match.group(1).upper()
        binding = db_get_board_binding_for_channel(data_dir, channel_id)
        if not binding:
            return AssistantResponse.from_text(
                "No board linked to this channel yet. "
                "Say `@alfred link board to F0123…` first."
            )
        updated = db_update_board_binding(
            data_dir,
            binding["id"],
            display_id_prefix=prefix,
        )
        row = updated or binding
        return AssistantResponse.from_text(
            f"Display id prefix set to **{row['display_id_prefix']}**; "
            f"next id will be `{row['display_id_prefix']}-{row['next_display_num']}`."
        )

    if _SHOW_CONFIG_RE.search(text):
        binding = db_get_board_binding_for_channel(data_dir, channel_id)
        from backend.db.slack_workflows_db import db_get_channel_workflow

        workflow = db_get_channel_workflow(data_dir, channel_id)
        if not binding and not workflow:
            return AssistantResponse.from_text(
                "No board or channel workflow configured for this channel. "
                "Link a list with `@alfred link board to F0123…` or use **Settings → Slack boards**."
            )
        lines = ["**Channel workflow**"]
        if workflow:
            lines.append(f"- Ticket system: `{workflow.get('ticket_system', 'ask')}`")
            if workflow.get("jira_project_key"):
                lines.append(f"- JIRA project: `{workflow['jira_project_key']}`")
        else:
            lines.append("- Ticket system: `ask` (default)")
        if binding:
            lines.extend(
                [
                    "",
                    "**Board binding**",
                    f"- Board key: `{binding['board_key']}`",
                    f"- List id: `{binding['list_id']}`",
                    f"- Display prefix: `{binding['display_id_prefix']}`",
                    f"- Next number: `{binding['next_display_num']}` → `{binding['display_id_prefix']}-{binding['next_display_num']}`",
                    f"- Default status: `{binding['default_status']}`",
                    f"- Auto-approve writes: `{binding['auto_approve_writes']}`",
                ]
            )
        return AssistantResponse.from_text("\n".join(lines))

    return None
