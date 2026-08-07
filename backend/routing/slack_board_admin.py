"""In-Slack admin commands for board/channel workflow configuration (writes to DB)."""

from __future__ import annotations

import re

from backend.db.slack_workflows_db import (
    db_create_board_binding,
    db_delete_board_binding,
    db_get_board_binding_for_channel,
    db_get_channel_workflow,
    db_update_board_binding,
    db_upsert_channel_workflow,
)
from backend.db.slack_board_store import SlackBoardStore
from backend.integrations.slack.board_keys import derive_board_key, fetch_slack_channel_name
from backend.routing.slack_board_intent import is_placeholder_list_id
from backend.models.config import AlfredConfig
from backend.models.response import AssistantResponse
from backend.models.task import Task

_LINK_BOARD_RE = re.compile(
    r"\b(?:link|bind|connect)\b.{0,20}\b(?:board|list|channel)\b.{0,40}\b(?:to\s+)?(F[A-Za-z0-9]+)\b",
    re.I,
)
_UNLINK_BOARD_RE = re.compile(
    r"\b(?:unlink|unbind|delink|disconnect|remove)\b.{0,20}\b(?:board|list)\b",
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
_CONFIG_STATUS_RE = re.compile(
    r"\b(?:configured|setup|set up|ready|linked|bound)\b.{0,40}\b(?:track|assign|task|ticket|board|list)\b"
    r"|\bcan you see if\b.{0,60}\b(?:configured|setup|track|assign|task|ticket|board|list)\b"
    r"|\b(?:is|are)\s+(?:this|we|it|alfred|the channel)\b.{0,40}\b(?:configured|setup|ready|linked)\b"
    r"|\b(?:does|do)\s+(?:this|alfred|we)\b.{0,30}\b(?:track|assign)\b.{0,20}\b(?:task|ticket)\b",
    re.I,
)


def format_channel_board_status(data_dir, channel_id: str) -> str:
    from backend.db.slack_workflows_db import db_get_channel_workflow

    binding = db_get_board_binding_for_channel(data_dir, channel_id)
    workflow = db_get_channel_workflow(data_dir, channel_id)
    if not binding and not workflow:
        return (
            "**Not configured** for this channel yet.\n\n"
            "To enable Slack List task tracking:\n"
            "1. `@alfred link board to F0123…` (List id from your Task List tab), or\n"
            "2. **Settings → Automation → Slack boards** → Add board binding\n\n"
            "Then ask `@alfred create task for … for above` in a thread."
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
                f"- Next number: `{binding['next_display_num']}` → "
                f"`{binding['display_id_prefix']}-{binding['next_display_num']}`",
                f"- Default status: `{binding['default_status']}`",
                f"- Auto-approve writes: `{binding['auto_approve_writes']}`",
                "",
                "This channel **can** track and assign tasks via `@alfred` when the List is linked.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "**Board binding:** not linked — add a List binding to create/track tasks.",
            ]
        )
    return "\n".join(lines)


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

    if _UNLINK_BOARD_RE.search(text):
        binding = db_get_board_binding_for_channel(data_dir, channel_id)
        if not binding:
            return AssistantResponse.from_text(
                "This channel has no board binding to remove. "
                "Use `@alfred show board config` to confirm."
            )
        list_id = str(binding.get("list_id") or "")
        board_key = str(binding.get("board_key") or "board")
        deleted = db_delete_board_binding(data_dir, str(binding["id"]))
        fresh = db_get_board_binding_for_channel(data_dir, channel_id)
        if not deleted or fresh is not None:
            return AssistantResponse.from_text(
                "Could not remove the board binding from the database. "
                "Try **Settings → Automation → Slack boards**, or try again."
            )
        store = SlackBoardStore(data_dir)
        if list_id:
            store.clear_schema_cache(list_id)
        return AssistantResponse.from_text(
            f"Removed the board binding for this channel (`{board_key}` → List `{list_id}`). "
            "Task create/update for this channel is disabled until you link again. "
            "Confirm with `@alfred show board config`."
        )

    match = _LINK_BOARD_RE.search(text)
    if match:
        list_id = match.group(1)
        if is_placeholder_list_id(list_id):
            return AssistantResponse.from_text(
                f"`{list_id}` looks like a placeholder List id from docs or the admin UI, not your real List. "
                "Open the channel **Task List** tab and copy the **F…** id from the browser URL."
            )
        token = (config.slack.bot_token or "").strip()
        if token:
            from slack_sdk import WebClient

            from backend.integrations.slack.lists_client import verify_list_id

            ok, verify_msg = verify_list_id(WebClient(token=token), list_id)
            if not ok:
                return AssistantResponse.from_text(verify_msg)
        name_match = re.search(r"\bfor\s+([a-z0-9_-]{2,40})\b", text, re.I)
        existing = db_get_board_binding_for_channel(data_dir, channel_id)
        channel_name = fetch_slack_channel_name(config, channel_id)
        if name_match:
            board_key = name_match.group(1).lower()
        elif existing:
            board_key = str(existing["board_key"])
        else:
            board_key = derive_board_key(channel_name=channel_name, channel_id=channel_id)
        if existing:
            update_fields: dict[str, str] = {"list_id": list_id}
            if name_match:
                update_fields["board_key"] = board_key
            if channel_name:
                update_fields["channel_name"] = channel_name
            updated = db_update_board_binding(
                data_dir,
                existing["id"],
                **update_fields,
            )
            if not updated:
                return AssistantResponse.from_text(
                    "Could not update the board binding in the database. "
                    "Try again or edit the binding in **Settings → Slack boards**."
                )
            binding = updated
        else:
            binding = db_create_board_binding(
                data_dir,
                board_key=board_key,
                list_id=list_id,
                channel_id=channel_id,
                channel_name=channel_name,
            )
        fresh = db_get_board_binding_for_channel(data_dir, channel_id)
        if not fresh or str(fresh.get("list_id") or "") != list_id:
            return AssistantResponse.from_text(
                f"Board link did not persist list `{list_id}`. "
                "Check **Settings → Slack boards** or try `@alfred show board config`."
            )
        binding = fresh
        store = SlackBoardStore(data_dir)
        if existing and str(existing.get("list_id") or "") != list_id:
            store.clear_schema_cache(str(existing.get("list_id") or ""))
        store.clear_schema_cache(list_id)
        workflow = db_get_channel_workflow(data_dir, channel_id)
        if not workflow:
            db_upsert_channel_workflow(
                data_dir,
                channel_id=channel_id,
                ticket_system="slack_list",
            )
        return AssistantResponse.from_text(
            "Linked this channel to Slack List "
            f"`{binding['list_id']}` as board **{binding['board_key']}**. "
            f"Display prefix `{binding['display_id_prefix']}`, next id `{binding['display_id_prefix']}-{binding['next_display_num']}`. "
            "Board key is per-channel (auto from channel name unless you say `for my-key`). "
            "Confirm with `@alfred show board config`, then create your task."
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

    if _SHOW_CONFIG_RE.search(text) or _CONFIG_STATUS_RE.search(text):
        return AssistantResponse.from_text(
            format_channel_board_status(data_dir, channel_id)
        )

    return None
