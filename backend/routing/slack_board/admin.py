"""In-Slack admin commands for board/channel workflow configuration (writes to DB)."""

from __future__ import annotations

import re

from backend.db.slack_workflows_db import (
    db_create_board_binding,
    db_delete_board_bindings_for_channel,
    db_get_board_binding_for_channel,
    db_get_board_binding_for_list_id,
    db_get_channel_workflow,
    db_list_board_bindings_for_channel,
    db_update_board_binding,
    db_upsert_channel_workflow,
)
from backend.db.slack_board_store import SlackBoardStore
from backend.integrations.slack.board_keys import (
    derive_board_key,
    derive_list_name,
    fetch_slack_channel_name,
)
from backend.routing.slack_board.intent import (
    extract_setup_board_custom_name,
    is_placeholder_list_id,
    looks_like_setup_board_command,
)
from backend.models.config import AlfredConfig
from backend.models.response import AssistantResponse
from backend.models.task import Task

_LINK_BOARD_RE = re.compile(
    r"\b(?:link|bind|connect)\b.{0,20}\b(?:board|list|channel)\b.{0,40}\b(?:to\s+)?(F[A-Za-z0-9]+)\b",
    re.I,
)
_UNLINK_BOARD_RE = re.compile(
    r"^\s*(?:unlink|unbind|delink|disconnect)(?:\s+(?:the\s+)?(?:board|list|binding))?\s*$"
    r"|\b(?:unlink|unbind|delink|disconnect|remove)\b.{0,20}\b(?:board|list)\b",
    re.I,
)
_SET_PREFIX_RE = re.compile(
    r"\b(?:set|change|update)\b.{0,40}\b(?:display\s*)?(?:id\s*)?prefix\b"
    r"(?:\s+to\s+|\s*[:=]\s*|\s+)([A-Z]{1,8})\b",
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
    r"\b(?:configured|ready|linked|bound)\b.{0,40}\b(?:track|assign|task|ticket|board|list)\b"
    r"|\bcan you see if\b.{0,60}\b(?:configured|setup|track|assign|task|ticket|board|list)\b"
    r"|\b(?:is|are)\s+(?:this|we|it|alfred|the channel)\b.{0,40}\b(?:configured|setup|ready|linked)\b"
    r"|\b(?:does|do)\s+(?:this|alfred|we)\b.{0,30}\b(?:track|assign)\b.{0,20}\b(?:task|ticket)\b",
    re.I,
)

_SHARE_BOARD_RE = re.compile(
    r"\bshare\b.{0,40}\b(?:the\s+)?(?:board|list)\b",
    re.I,
)


def _ensure_slack_list_workflow(data_dir, channel_id: str) -> None:
    workflow = db_get_channel_workflow(data_dir, channel_id)
    if not workflow:
        db_upsert_channel_workflow(
            data_dir,
            channel_id=channel_id,
            ticket_system="slack_list",
        )


def _upsert_channel_board_binding(
    data_dir,
    *,
    channel_id: str,
    list_id: str,
    board_key: str,
    channel_name: str = "",
    list_name: str = "",
    columns: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Create or update the single board binding for a channel."""
    existing = db_get_board_binding_for_channel(data_dir, channel_id)
    store = SlackBoardStore(data_dir)
    if existing:
        old_list_id = str(existing.get("list_id") or "")
        update_fields: dict[str, Any] = {
            "list_id": list_id,
            "board_key": board_key,
        }
        if channel_name:
            update_fields["channel_name"] = channel_name
        if list_name:
            update_fields["list_name"] = list_name
        if columns:
            update_fields["columns"] = columns
        binding = db_update_board_binding(data_dir, str(existing["id"]), **update_fields)
        if old_list_id and old_list_id != list_id:
            store.clear_schema_cache(old_list_id)
    else:
        create_kwargs: dict[str, Any] = {
            "board_key": board_key,
            "list_id": list_id,
            "channel_id": channel_id,
            "channel_name": channel_name,
            "list_name": list_name,
        }
        if columns:
            create_kwargs["columns"] = columns
        binding = db_create_board_binding(data_dir, **create_kwargs)
    store.clear_schema_cache(list_id)
    fresh = db_get_board_binding_for_channel(data_dir, channel_id)
    if not fresh or str(fresh.get("list_id") or "") != list_id:
        return None
    _ensure_slack_list_workflow(data_dir, channel_id)
    return fresh or binding


def format_channel_board_status(data_dir, channel_id: str) -> str:
    from backend.db.slack_workflows_db import db_get_channel_workflow

    bindings = db_list_board_bindings_for_channel(data_dir, channel_id)
    binding = bindings[0] if bindings else None
    workflow = db_get_channel_workflow(data_dir, channel_id)
    if not bindings and not workflow:
        return (
            "**Not configured** for this channel yet.\n\n"
            "To enable Slack List task tracking:\n"
            "1. **`@alfred setup board`** — Alfred creates the List, grants access, and links this channel (recommended), or\n"
            "2. `@alfred link board to F…` (List id from your Task List tab), or\n"
            "3. **Settings → Automation → Slack boards** → Add board binding\n\n"
            "To share a linked List so it appears under **Shared with you**: `@alfred share board with @user`.\n"
            "To remove a binding: `@alfred unlink` or `@alfred unlink board`.\n\n"
            "Then ask `@alfred create task for …` in a thread."
        )
    lines = ["**Channel workflow**"]
    if workflow:
        lines.append(f"- Ticket system: `{workflow.get('ticket_system', 'ask')}`")
        if workflow.get("jira_project_key"):
            lines.append(f"- JIRA project: `{workflow['jira_project_key']}`")
    else:
        lines.append("- Ticket system: `ask` (default)")
    if binding:
        if len(bindings) > 1:
            lines.extend(
                [
                    "",
                    f"**Warning:** {len(bindings)} board bindings found for this channel "
                    "(only one should exist). Remove extras in **Settings → Slack boards** "
                    "or run `@alfred unlink`.",
                ]
            )
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
                f"- Docs search: `{'on' if binding.get('docs_search_enabled') else 'off'}`",
            ]
        )
        persona = str(binding.get("persona_prompt") or "").strip()
        if persona:
            lines.extend(["- Persona:", f"  {persona}"])
        if len(bindings) > 1:
            lines.append("")
            lines.append("**All bindings for this channel:**")
            for row in bindings:
                active = "active" if row.get("enabled") else "disabled"
                lines.append(
                    f"- `{row['list_id']}` / `{row['board_key']}` ({active}, id `{row['id'][:8]}…`)"
                )
        lines.extend(
            [
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
        bindings = db_list_board_bindings_for_channel(data_dir, channel_id)
        if not bindings:
            return AssistantResponse.from_text(
                "This channel has no board binding to remove. "
                "Use `@alfred show board config` to confirm."
            )
        removed = db_delete_board_bindings_for_channel(data_dir, channel_id)
        fresh = db_list_board_bindings_for_channel(data_dir, channel_id)
        if removed <= 0 or fresh:
            return AssistantResponse.from_text(
                "Could not remove the board binding from the database. "
                "Try **Settings → Automation → Slack boards**, or try again."
            )
        store = SlackBoardStore(data_dir)
        for row in bindings:
            list_id = str(row.get("list_id") or "")
            if list_id:
                store.clear_schema_cache(list_id)
        if len(bindings) == 1:
            row = bindings[0]
            summary = (
                f"Removed the board binding for this channel "
                f"(`{row.get('board_key')}` → List `{row.get('list_id')}`)."
            )
        else:
            summary = f"Removed **{removed}** board bindings for this channel."
        return AssistantResponse.from_text(
            f"{summary} Task create/update for this channel is disabled until you link again. "
            "Run `@alfred setup board` or `@alfred link board to F…`. "
            "Confirm with `@alfred show board config`."
        )

    if _SHARE_BOARD_RE.search(text):
        token = (config.slack.bot_token or "").strip()
        if not token:
            return AssistantResponse.from_text(
                "Slack bot token is not configured — cannot share the List."
            )
        binding = db_get_board_binding_for_channel(data_dir, channel_id)
        if not binding:
            return AssistantResponse.from_text(
                "This channel has no linked List yet. Run **`@alfred setup board`** first."
            )
        from slack_sdk import WebClient

        from backend.integrations.slack.lists_client import list_open_url, share_list_with_users
        from backend.integrations.slack.sanitize import extract_slack_user_ids

        list_id = str(binding.get("list_id") or "")
        list_name = str(binding.get("list_name") or binding.get("board_key") or "Board")
        client = WebClient(token=token)
        user_ids = extract_slack_user_ids(task.raw_text or text)
        if not user_ids and task.user_id:
            user_ids = [task.user_id]
        if not user_ids:
            return AssistantResponse.from_text(
                "Who should I share the List with? Example: "
                "`@alfred share board with @yourself`"
            )
        share_notes = share_list_with_users(
            client,
            list_id,
            user_ids,
            channel_id=channel_id,
        )
        open_url = list_open_url(client, list_id)
        mention_text = ", ".join(f"<@{uid}>" for uid in user_ids)
        lines = [
            f"Shared List **`{list_name}`** (`{list_id}`) with {mention_text} (**Can edit**).",
            "",
            "**Add to this channel tab:** **+** → **List** → check **Shared with you**.",
        ]
        if open_url:
            lines.extend(["", f"**Open List:** {open_url}"])
        if share_notes:
            lines.extend(["", "Notes:", *[f"- {note}" for note in share_notes]])
        return AssistantResponse.from_text("\n".join(lines))

    if looks_like_setup_board_command(text):
        token = (config.slack.bot_token or "").strip()
        if not token:
            return AssistantResponse.from_text(
                "Slack bot token is not configured — cannot create a List."
            )
        from slack_sdk import WebClient

        from backend.integrations.slack.lists_client import (
            ALFRED_BOARD_COLUMN_MAP,
            SlackListAccessError,
            list_open_url,
            provision_alfred_board_list,
            try_add_list_bookmark,
        )

        existing = db_get_board_binding_for_channel(data_dir, channel_id)
        force_new = bool(re.search(r"\b(?:force|new|replace)\b", text, re.I))
        client = WebClient(token=token)
        if existing and not force_new:
            list_id = str(existing.get("list_id") or "")
            list_name = str(existing.get("list_name") or existing.get("board_key") or "board")
            open_url = list_open_url(client, list_id) if list_id else ""
            lines = [
                f"This channel is already linked to List **`{list_name}`** (`{list_id}`).",
                "",
                "Tasks are added to **that** List — your channel tab may show a different one.",
                "Copy **F…** from the channel tab URL and run `@alfred link board to F…` to use the tab you see.",
                "",
                "Try **`@alfred create task for smoke test`** now.",
            ]
            if open_url:
                lines.extend(["", f"**Open linked List:** {open_url}"])
            return AssistantResponse.from_text("\n".join(lines))

        custom_name = extract_setup_board_custom_name(text)
        channel_name = fetch_slack_channel_name(config, channel_id)
        list_name = custom_name or derive_list_name(
            channel_name=channel_name,
            channel_id=channel_id,
        )
        board_key = derive_board_key(channel_name=channel_name, channel_id=channel_id)
        store = SlackBoardStore(data_dir) if data_dir else SlackBoardStore(None)
        try:
            list_id, grant_notes, open_url = provision_alfred_board_list(
                client,
                channel_id=channel_id,
                list_name=list_name,
                requesting_user_id=task.user_id or "",
                schema_cache=store,
            )
        except SlackListAccessError as exc:
            return AssistantResponse.from_text(str(exc))
        except RuntimeError as exc:
            return AssistantResponse.from_text(
                f"Could not create Slack List: {exc}\n\n"
                "Ensure Alfred has **`lists:write`** and **`lists:read`**, then reinstall the Slack app."
            )

        binding = _upsert_channel_board_binding(
            data_dir,
            channel_id=channel_id,
            list_id=list_id,
            board_key=board_key,
            channel_name=channel_name,
            list_name=list_name,
            columns=ALFRED_BOARD_COLUMN_MAP,
        )
        if not binding:
            return AssistantResponse.from_text(
                f"Created List `{list_id}` but could not save the channel binding. "
                "Try again or add it in **Settings → Slack boards**."
            )
        if not open_url:
            open_url = list_open_url(client, list_id)
        try_add_list_bookmark(
            client,
            channel_id=channel_id,
            title=list_name,
            url=open_url,
        )
        lines = [
            f"Created and linked Slack List **`{list_name}`** (`{list_id}`) for this channel.",
            f"- Board key: **{binding['board_key']}**",
            f"- Display prefix: `{binding['display_id_prefix']}` → next id `{binding['display_id_prefix']}-{binding['next_display_num']}`",
            "",
            "Try **`@alfred create task for smoke test`** now.",
            "",
            "**Important:** If this channel already has a List tab, open it and copy **F…** from the URL, "
            "then run `@alfred link board to F…` so tasks appear where you look.",
            "",
            "**Open the List:**",
            f"- Direct link: {open_url}" if open_url else f"- List id: `{list_id}`",
            f"- Slack sidebar → **Lists** → **{list_name}** (you are the List owner)",
            f"- In this channel: **+** → **List** → **{list_name}**",
        ]
        if grant_notes:
            lines.extend(["", "Notes:", *[f"- {note}" for note in grant_notes]])
        return AssistantResponse.from_text("\n".join(lines))

    match = _LINK_BOARD_RE.search(text)
    if match:
        list_id = match.group(1)
        if is_placeholder_list_id(list_id):
            return AssistantResponse.from_text(
                f"`{list_id}` looks like a placeholder List id from docs or the admin UI, not your real List. "
                "Open the channel **Task List** tab and copy the **F…** id from the browser URL."
            )
        other = db_get_board_binding_for_list_id(
            data_dir,
            list_id,
            exclude_channel_id=channel_id,
        )
        if other:
            other_channel = other.get("channel_name") or other.get("channel_id") or "another channel"
            return AssistantResponse.from_text(
                f"Slack List `{list_id}` is already linked to **{other_channel}**. "
                "Run `@alfred unlink` in that channel first, or remove the binding in "
                "**Settings → Automation → Slack boards**."
            )
        token = (config.slack.bot_token or "").strip()
        if not token:
            return AssistantResponse.from_text(
                "Slack bot token is not configured — cannot verify List access before linking."
            )
        from slack_sdk import WebClient

        from backend.integrations.slack.lists_client import verify_list_id

        ok, verify_msg = verify_list_id(
            WebClient(token=token),
            list_id,
            channel_id=channel_id,
        )
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
        from backend.integrations.slack.lists_client import ALFRED_BOARD_COLUMN_MAP

        binding = _upsert_channel_board_binding(
            data_dir,
            channel_id=channel_id,
            list_id=list_id,
            board_key=board_key,
            channel_name=channel_name,
            columns=ALFRED_BOARD_COLUMN_MAP,
        )
        if not binding:
            return AssistantResponse.from_text(
                f"Board link did not persist list `{list_id}`. "
                "Check **Settings → Slack boards** or try `@alfred show board config`."
            )
        from backend.integrations.slack.lists_client import list_open_url

        open_url = list_open_url(WebClient(token=token), str(binding["list_id"]))
        channel_label = channel_name or channel_id
        lines = [
            f"Linked **#{channel_label}** to Slack List `{binding['list_id']}` as board **{binding['board_key']}**.",
            f"- Display prefix: `{binding['display_id_prefix']}` → next id `{binding['display_id_prefix']}-{binding['next_display_num']}`",
            f"- Ticket system: `slack_list` (set automatically)",
        ]
        if open_url:
            lines.append(f"- Open List: {open_url}")
        lines.extend(
            [
                "",
                "Tasks you create with `@alfred create task …` will land in **this** List.",
                "If your channel tab shows a **different** List, copy the **F…** id from that tab's URL and run `@alfred link board to F…` again.",
                "Confirm anytime with `@alfred show board config`.",
            ]
        )
        return AssistantResponse.from_text("\n".join(lines))

    match = _SET_PREFIX_RE.search(text)
    if match:
        prefix = match.group(1).upper()
        binding = db_get_board_binding_for_channel(data_dir, channel_id)
        if not binding:
            return AssistantResponse.from_text(
                "No board linked to this channel yet. "
                "Say `@alfred setup board` or `@alfred link board to F0123…` first."
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
