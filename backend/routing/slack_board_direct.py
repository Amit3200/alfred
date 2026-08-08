"""Direct Slack board create/status — no agent loop required."""

from __future__ import annotations

import logging
import re
from typing import Any

from backend.db.slack_workflows_db import db_update_board_binding
from backend.integrations.slack.board_service import board_enabled, create_board_task, update_board_task
from backend.integrations.slack.workflow_registry import (
    binding_to_profile,
    fresh_board_binding_for_channel,
)
from backend.integrations.slack.sanitize import extract_slack_user_ids
from backend.models.config import AlfredConfig
from backend.models.response import AssistantResponse
from backend.models.task import Task
from backend.routing.slack_board_intent import (
    build_thread_description,
    extract_board_title_followup,
    extract_list_id_override,
    extract_severity_target,
    extract_status_target,
    extract_task_title,
    extract_ticket_ref,
    is_placeholder_list_id,
    looks_like_board_create_title_followup,
    looks_like_board_where_question,
    looks_like_slack_board_create,
    looks_like_slack_board_followup,
    looks_like_slack_board_update,
    references_thread_context,
    resolve_ticket_ref,
)

logger = logging.getLogger(__name__)

_SEVERITY_RE = re.compile(r"\b(p0|p1|p2|p3)\b", re.I)
_TICKET_REF_IN_TEXT_RE = re.compile(r"\b((?:TS|BUG|TK|T)-\d+|Rec[A-Za-z0-9]+)\b", re.I)
_ASSIGN_ME_RE = re.compile(r"\bassign\b.{0,24}\b(?:it\s+)?to\s+me\b", re.I)


def extract_board_create_fields(task: Task, *, bot_user_id: str = "") -> dict[str, str]:
    """Parse title, severity, and assignee from a create-task message."""
    intent = task.cleaned_intent or task.raw_text or ""
    title = extract_task_title(intent).strip()
    if not title:
        title = extract_task_title(task.raw_text or "").strip()
    severity = ""
    sev_match = _SEVERITY_RE.search(intent)
    if sev_match:
        severity = sev_match.group(1).upper()
        title = _SEVERITY_RE.sub("", title).strip(" .,:;-")
        title = re.sub(r"\s+as\s*$", "", title, flags=re.I).strip()
    title = re.sub(
        r"\s+and\s+assign\b.*$",
        "",
        title,
        flags=re.I,
    ).strip(" .,:;-")
    assignee_user_id = ""
    if _ASSIGN_ME_RE.search(intent) and task.user_id:
        assignee_user_id = task.user_id
    else:
        user_ids = extract_slack_user_ids(task.raw_text or intent)
        user_ids = [uid for uid in user_ids if uid and uid != bot_user_id]
        if user_ids:
            assignee_user_id = user_ids[-1]
    return {
        "title": title[:200],
        "severity": severity,
        "assignee_user_id": assignee_user_id,
    }


def format_board_task_created(result: dict[str, Any], *, severity: str = "", assignee_user_id: str = "") -> str:
    display_id = result.get("display_id") or ""
    title = result.get("title") or "Task"
    status = result.get("status") or "Not picked"
    list_id = result.get("list_id") or ""
    list_name = result.get("list_name") or result.get("board") or "board"
    record_id = result.get("record_id") or ""
    lines = [
        f"**Task created on your board** — **{display_id or record_id}** · *{title}*",
        f"- List: **{list_name}** (`{list_id}`)" if list_id else f"- Board: `{list_name}`",
        f"- Status: `{status}`",
    ]
    if severity:
        lines.append(f"- Severity: `{severity}`")
    if assignee_user_id:
        lines.append(f"- Assignee: `<@{assignee_user_id}>`")
    lines.append(f"- Record: `{result.get('record_id')}`")
    open_url = (result.get("open_url") or "").strip()
    if open_url:
        lines.append(f"- Open List: {open_url}")
    return "\n".join(lines)


def _placeholder_binding_message(list_id: str) -> str:
    return (
        f"This channel is linked to placeholder List id `{list_id}`, not a real Slack List. "
        "Run **`@alfred setup board`** or `@alfred link board to F…` with the id from your Task List tab URL."
    )


def _resolve_board_for_create(
    *,
    config: AlfredConfig,
    data_dir: Any,
    channel_id: str,
    intent: str,
    client: Any,
    store: Any,
) -> tuple[Any | None, AssistantResponse | None]:
    """Resolve board profile for create, honoring explicit list id overrides."""
    from backend.models.config import SlackBoardProfile

    binding = fresh_board_binding_for_channel(data_dir, channel_id)
    board = binding_to_profile(binding) if binding else None
    list_override = extract_list_id_override(intent)

    if list_override:
        if is_placeholder_list_id(list_override):
            return None, AssistantResponse.from_text(
                f"`{list_override}` looks like a placeholder List id from docs or the admin UI. "
                "Use the **F…** id from your Task List tab URL."
            )
        from backend.integrations.slack.lists_client import verify_list_id

        ok, verify_msg = verify_list_id(client, list_override, channel_id=channel_id)
        if not ok:
            return None, AssistantResponse.from_text(verify_msg)

        if binding and str(binding.get("list_id") or "") != list_override:
            old_list_id = str(binding.get("list_id") or "")
            updated = db_update_board_binding(
                data_dir,
                str(binding["id"]),
                list_id=list_override,
            )
            binding = updated or fresh_board_binding_for_channel(data_dir, channel_id)
            if old_list_id:
                store.clear_schema_cache(old_list_id)
            store.clear_schema_cache(list_override)

        if binding:
            board = binding_to_profile(binding)
        else:
            from backend.integrations.slack.board_keys import derive_board_key, fetch_slack_channel_name

            board = SlackBoardProfile(
                name=derive_board_key(
                    channel_name=fetch_slack_channel_name(config, channel_id),
                    channel_id=channel_id,
                ),
                list_id=list_override,
                channel_ids=[channel_id],
            )

        if board.list_id != list_override:
            board = board.model_copy(update={"list_id": list_override})
        return board, None

    if board is None:
        return None, AssistantResponse.from_text(
            "This channel is not linked to a Slack List yet. "
            "Say **`@alfred setup board`** (recommended), `@alfred link board to F…`, "
            "or `@alfred create task for … on list F…`."
        )
    bound_list_id = (board.list_id or "").strip()
    if not bound_list_id:
        return None, AssistantResponse.from_text(
            "This channel's board binding has no List id. "
            "Run `@alfred link board to F…` with the id from your Task List tab URL."
        )
    if is_placeholder_list_id(bound_list_id):
        return None, AssistantResponse.from_text(_placeholder_binding_message(bound_list_id))
    return board, None


def try_slack_board_create_direct(
    task: Task,
    config: AlfredConfig,
    data_dir: Any,
    *,
    session: Any | None = None,
    session_turns: tuple[str, ...] = (),
    force_intent_class: str = "",
    title_override: str = "",
) -> tuple[AssistantResponse | None, dict[str, Any]]:
    """Create a list task immediately when the user asks (Slack only)."""
    if task.source != "slack" or not config.slack.enabled:
        return None, {}

    intent = task.cleaned_intent or task.raw_text or ""
    session_meta = dict((session.metadata if session else {}) or {})
    title_followup = looks_like_board_create_title_followup(
        intent,
        session_turns=session_turns,
        session_metadata=session_meta,
    )
    if not looks_like_slack_board_create(intent) and not title_followup:
        if force_intent_class != "slack.board.create":
            return None, {}

    if not board_enabled(config, data_dir):
        return (
            AssistantResponse.from_text(
                "Slack List boards are not configured yet. "
                "Say **`@alfred setup board`** or use **Settings → Slack boards**."
            ),
            {},
        )

    if not title_followup and not title_override and force_intent_class != "slack.board.create":
        preliminary_title = extract_task_title(intent)
        if not preliminary_title:
            preliminary_title = extract_task_title(task.raw_text or "")
        if not preliminary_title and not references_thread_context(intent):
            return (
                AssistantResponse.from_text(
                    "What should the task be called? Reply with the title, for example: "
                    "**Talk to CottonThreads** or `@alfred create task for payment delay`."
                ),
                {"pending_board_create": True},
            )

    token = (config.slack.bot_token or "").strip()
    if not token:
        return AssistantResponse.error("Slack bot token is not configured."), {}

    from slack_sdk import WebClient

    from backend.db.slack_board_store import SlackBoardStore
    from backend.integrations.slack.context import fetch_thread_messages, messages_to_text
    from backend.routing.slack_board_bootstrap import _bot_user_id

    client = WebClient(token=token)
    store = SlackBoardStore(data_dir) if data_dir else SlackBoardStore(None)
    channel_id = task.channel_id or ""

    board, resolve_error = _resolve_board_for_create(
        config=config,
        data_dir=data_dir,
        channel_id=channel_id,
        intent=intent,
        client=client,
        store=store,
    )
    if resolve_error is not None:
        return resolve_error, {}

    binding = fresh_board_binding_for_channel(data_dir, channel_id)
    if binding:
        bound_list_id = str(binding.get("list_id") or "").strip()
        if bound_list_id and board.list_id != bound_list_id:
            board = board.model_copy(update={"list_id": bound_list_id})
            store.clear_schema_cache(bound_list_id)

    fields = extract_board_create_fields(task, bot_user_id=_bot_user_id(client))
    if title_followup:
        title = extract_board_title_followup(intent)
        severity = fields["severity"]
        assignee_user_id = fields["assignee_user_id"]
    elif title_override:
        title = title_override.strip()[:200]
        severity = fields["severity"]
        assignee_user_id = fields["assignee_user_id"]
    else:
        title = fields["title"]
        severity = fields["severity"]
        assignee_user_id = fields["assignee_user_id"]
    if not title and references_thread_context(intent):
        title = (task.cleaned_intent or "Slack thread task")[:120].strip()
    if not title:
        return (
            AssistantResponse.from_text(
                "What should the task be called? Reply with the title, for example: "
                "**Talk to CottonThreads** or `@alfred create task for payment delay`."
            ),
            {"pending_board_create": True},
        )

    description = "Created from Slack conversation."
    if task.channel_id and task.thread_ts:
        try:
            messages = fetch_thread_messages(
                client,
                task,
                limit=50,
                bot_user_id=_bot_user_id(client),
            )
            if messages:
                description = build_thread_description(messages_to_text(messages))
        except Exception as exc:
            logger.warning("Thread fetch for direct board create failed: %s", exc)

    try:
        result = create_board_task(
            client,
            config,
            store,
            board,
            title=title,
            description=description,
            severity=severity,
            assignee_user_id=assignee_user_id,
            channel_id=task.channel_id or "",
            thread_ts=task.thread_ts or "",
        )
    except Exception as exc:
        logger.exception("Direct Slack board create failed")
        return AssistantResponse.error(f"Could not create board task: {exc}"), {}

    from backend.integrations.slack.lists_client import list_open_url

    list_name = str((binding or {}).get("list_name") or board.name or "")
    result = {
        **result,
        "list_name": list_name,
        "open_url": list_open_url(client, result.get("list_id") or "") if result.get("list_id") else "",
    }

    body = format_board_task_created(
        result,
        severity=severity,
        assignee_user_id=assignee_user_id,
    )
    metadata = {
        "pending_board_create": False,
        "last_board_task": {
            "display_id": result.get("display_id"),
            "record_id": result.get("record_id"),
            "title": result.get("title"),
            "status": result.get("status"),
            "board": result.get("board"),
            "list_id": result.get("list_id"),
            "list_name": result.get("list_name"),
            "open_url": result.get("open_url"),
        }
    }
    return AssistantResponse.from_text(body), metadata


def extract_board_update_fields(
    task: Task,
    *,
    session_metadata: dict[str, Any] | None = None,
    bot_user_id: str = "",
) -> dict[str, str]:
    """Parse ticket ref, status, severity, and assignee from an update/assign message."""
    intent = task.cleaned_intent or task.raw_text or ""
    ticket_ref = resolve_ticket_ref(intent, session_metadata=session_metadata)
    status = extract_status_target(intent)
    severity = extract_severity_target(intent)
    user_ids = extract_slack_user_ids(task.raw_text or intent)
    user_ids = [uid for uid in user_ids if uid and uid != bot_user_id]
    assignee_user_id = user_ids[-1] if user_ids else ""
    return {
        "ticket_ref": ticket_ref.strip(),
        "status": status.strip(),
        "severity": severity.strip(),
        "assignee_user_id": assignee_user_id.strip(),
    }


def format_board_task_updated(result: dict[str, Any]) -> str:
    updated = result.get("updated") or {}
    record_id = result.get("record_id") or ""
    lines = [f"Updated board task **`{record_id}`**"]
    if updated.get("status"):
        lines.append(f"- Status: `{updated['status']}`")
    if updated.get("assignee_user_id"):
        lines.append(f"- Assignee: `<@{updated['assignee_user_id']}>`")
    if updated.get("severity"):
        lines.append(f"- Severity: `{updated['severity']}`")
    return "\n".join(lines)


def try_slack_board_update_direct(
    task: Task,
    config: AlfredConfig,
    data_dir: Any,
    *,
    session: Any | None = None,
    force_intent_class: str = "",
    plan_fields: dict[str, str] | None = None,
) -> tuple[AssistantResponse | None, dict[str, Any]]:
    """Update status or assignee immediately when the user asks (Slack only)."""
    if task.source != "slack" or not config.slack.enabled:
        return None, {}
    if not looks_like_slack_board_update(task.cleaned_intent or ""):
        if force_intent_class != "slack.board.update":
            return None, {}

    if not board_enabled(config, data_dir):
        return (
            AssistantResponse.from_text(
                "Slack List boards are not configured yet. "
                "Say **`@alfred setup board`** first."
            ),
            {},
        )

    token = (config.slack.bot_token or "").strip()
    if not token:
        return AssistantResponse.error("Slack bot token is not configured."), {}

    from slack_sdk import WebClient

    from backend.db.slack_board_store import SlackBoardStore

    from backend.routing.slack_board_bootstrap import _bot_user_id

    client = WebClient(token=token)
    store = SlackBoardStore(data_dir) if data_dir else SlackBoardStore(None)
    session_meta = dict((session.metadata if session else {}) or {})
    fields = extract_board_update_fields(
        task,
        session_metadata=session_meta,
        bot_user_id=_bot_user_id(client),
    )
    for key, value in dict(plan_fields or {}).items():
        if value and key in fields and not fields[key]:
            fields[key] = value

    if not fields["ticket_ref"]:
        return (
            AssistantResponse.from_text(
                "Which task should I update? Use a display id like **`ST-1`** or **`TS-3`**, "
                "or say `@alfred assign this task to @user` right after creating one."
            ),
            {},
        )
    if not fields["status"] and not fields["assignee_user_id"] and not fields["severity"]:
        return (
            AssistantResponse.from_text(
                "What should I change? Examples:\n"
                "• `@alfred ST-1 is in progress`\n"
                "• `@alfred move ST-1 to in progress`\n"
                "• `@alfred assign ST-1 severity to High`\n"
                "• `@alfred assign ST-1 to @user`"
            ),
            {},
        )

    try:
        record_id_hint = ""
        last = dict(session_meta.get("last_board_task") or {})
        last_display = str(last.get("display_id") or "").upper()
        if last_display and last_display == fields["ticket_ref"].upper():
            record_id_hint = str(last.get("record_id") or "")

        result = update_board_task(
            client,
            config,
            store,
            ticket_ref=fields["ticket_ref"],
            status=fields["status"],
            assignee_user_id=fields["assignee_user_id"],
            severity=fields["severity"],
            channel_id=task.channel_id or "",
            record_id_hint=record_id_hint,
        )
    except Exception as exc:
        logger.exception("Direct Slack board update failed")
        return AssistantResponse.error(f"Could not update board task: {exc}"), {}

    body = format_board_task_updated(result)
    metadata: dict[str, Any] = {}
    last = dict(session_meta.get("last_board_task") or {})
    ticket_ref = fields["ticket_ref"].upper()
    last_ref = str(last.get("display_id") or last.get("record_id") or "").upper()
    if last_ref and last_ref == ticket_ref:
        if fields["status"]:
            last["status"] = fields["status"]
        metadata["last_board_task"] = last
    elif result.get("record_id"):
        metadata["last_board_task"] = {
            "display_id": fields["ticket_ref"],
            "record_id": result.get("record_id"),
            "status": fields["status"] or last.get("status") or "Not picked",
        }

    return AssistantResponse.from_text(body), metadata


def try_slack_board_where_direct(
    task: Task,
    config: AlfredConfig,
    data_dir: Any,
    *,
    session: Any | None = None,
) -> AssistantResponse | None:
    """Answer 'where is the task?' using the latest session task and List binding."""
    if task.source != "slack" or not config.slack.enabled:
        return None
    if not looks_like_board_where_question(task.cleaned_intent or ""):
        return None

    last = dict((session.metadata or {}).get("last_board_task") or {}) if session else {}
    if not last.get("display_id") and not last.get("record_id"):
        return AssistantResponse.from_text(
            "I don't see a task created in this thread yet. "
            "Ask `@alfred create task for …` first."
        )

    display = last.get("display_id") or last.get("record_id")
    title = last.get("title") or "Task"
    status = last.get("status") or "Not picked"
    list_id = str(last.get("list_id") or "").strip()
    list_name = str(last.get("list_name") or last.get("board") or "board")
    open_url = str(last.get("open_url") or "").strip()

    if not list_id and task.channel_id:
        binding = fresh_board_binding_for_channel(data_dir, task.channel_id or "")
        if binding:
            list_id = str(binding.get("list_id") or "").strip()
            list_name = str(binding.get("list_name") or list_name)

    verify_note = ""
    token = (config.slack.bot_token or "").strip()
    record_id = str(last.get("record_id") or "").strip()
    if token and list_id and record_id:
        from slack_sdk import WebClient

        from backend.integrations.slack.lists_client import get_item

        client = WebClient(token=token)
        if get_item(client, list_id, record_id) is None:
            verify_note = (
                f"\n\nNote: Slack API could not read record `{record_id}` in List `{list_id}`. "
                "Run `@alfred show board config` and confirm the channel List tab uses that id."
            )
        elif not open_url:
            from backend.integrations.slack.lists_client import list_open_url

            open_url = list_open_url(client, list_id)

    lines = [
        f"**{display}** — *{title}* is on List **{list_name}** (`{list_id or 'unknown'}`).",
        f"Status: `{status}`. Record: `{last.get('record_id') or display}`.",
    ]
    if open_url:
        lines.append(f"Open List: {open_url}")
    body = "\n".join(lines)
    if verify_note:
        body += verify_note
    return AssistantResponse.from_text(body)


def try_slack_board_status_followup(
    task: Task,
    config: AlfredConfig,
    data_dir: Any,
    *,
    session: Any | None = None,
    session_turns: tuple[str, ...] = (),
    thread_context: str | None = None,
) -> AssistantResponse | None:
    """Answer 'is it created?' style follow-ups from session state."""
    if task.source != "slack" or not config.slack.enabled:
        return None
    if not looks_like_slack_board_followup(
        task.cleaned_intent or "",
        session_turns=session_turns,
        thread_context=thread_context,
    ):
        return None

    last = {}
    if session is not None:
        last = dict((session.metadata or {}).get("last_board_task") or {})

    if not last:
        combined = "\n".join([*session_turns[-6:]])
        ref = _TICKET_REF_IN_TEXT_RE.search(combined)
        if ref:
            last = {"display_id": ref.group(1)}

    if last.get("display_id") or last.get("record_id"):
        display = last.get("display_id") or last.get("record_id")
        title = last.get("title") or "Task"
        status = last.get("status") or "Not picked"
        list_id = str(last.get("list_id") or "").strip()
        list_name = str(last.get("list_name") or last.get("board") or "board")
        open_url = str(last.get("open_url") or "").strip()
        lines = [
            f"Yes — **{display}** is on List **{list_name}** (`{list_id or 'unknown'}`): *{title}* (status `{status}`).",
        ]
        if open_url:
            lines.append(f"Open List: {open_url}")
        return AssistantResponse.from_text("\n".join(lines))

    return AssistantResponse.from_text(
        "I don't see a task created in this thread yet. "
        "Ask `@alfred create task for …` and I'll create it on the linked List immediately."
    )
