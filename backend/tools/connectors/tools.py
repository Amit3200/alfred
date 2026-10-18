"""Connector read tools — list chats/tickets/tasks/messages from registered connectors."""

from __future__ import annotations

from typing import Any

from backend.ai.base import ToolSchema
from backend.integrations.platform.registry import get_connector, list_connector_ids
from backend.tools.base.function_tool import FunctionTool
from backend.tools.base.tool import BaseTool, ToolContext
from backend.tools.result import ToolResult

CONNECTOR_LIST = ToolSchema(
    name="connector_list",
    description="List inbound connectors (e.g. periskope) that can pull WhatsApp tickets, tasks, and group messages.",
    parameters={"type": "object", "properties": {}},
)

CONNECTOR_LIST_CHATS = ToolSchema(
    name="connector_list_chats",
    description="List WhatsApp chats/groups from a connector (default: periskope).",
    parameters={
        "type": "object",
        "properties": {
            "connector_id": {
                "type": "string",
                "description": "Connector id. Default periskope.",
            },
        },
    },
)

CONNECTOR_LIST_TICKETS = ToolSchema(
    name="connector_list_tickets",
    description="List tickets from a connector (Periskope WhatsApp tickets).",
    parameters={
        "type": "object",
        "properties": {
            "connector_id": {"type": "string", "description": "Connector id. Default periskope."},
            "limit": {"type": "integer", "description": "Max tickets to return (default 30)."},
        },
    },
)

CONNECTOR_LIST_TASKS = ToolSchema(
    name="connector_list_tasks",
    description="List tasks from a connector (Periskope WhatsApp tasks).",
    parameters={
        "type": "object",
        "properties": {
            "connector_id": {"type": "string", "description": "Connector id. Default periskope."},
            "limit": {"type": "integer", "description": "Max tasks to return (default 30)."},
        },
    },
)

CONNECTOR_GET_MESSAGES = ToolSchema(
    name="connector_get_messages",
    description=(
        "Fetch WhatsApp messages from Periskope for a date window and/or one chat. "
        "chat_id is optional. For 'summarize all groups on 22 Aug' omit chat_id and "
        "pass start_time/end_time (YYYY-MM-DD or '22nd August'). Uses GET /chats/messages."
    ),
    parameters={
        "type": "object",
        "properties": {
            "connector_id": {"type": "string", "description": "Connector id. Default periskope."},
            "chat_id": {
                "type": "string",
                "description": "Optional WhatsApp chat id (…@g.us / …@c.us). Empty = all chats.",
            },
            "start_time": {
                "type": "string",
                "description": "Window start, e.g. 2026-08-22 or 22nd August.",
            },
            "end_time": {
                "type": "string",
                "description": "Window end, e.g. 2026-08-22. Defaults to start day / now.",
            },
            "limit": {"type": "integer", "description": "Max messages (default 200)."},
        },
    },
)

CONNECTOR_POLL = ToolSchema(
    name="connector_poll",
    description=(
        "Poll a connector over REST (no webhook needed). Default is a preview of tickets/tasks. "
        "Set replicate=true to create Slack List / JIRA items from the pull."
    ),
    parameters={
        "type": "object",
        "properties": {
            "connector_id": {"type": "string", "description": "Connector id. Default periskope."},
            "kinds": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Subset of tickets, tasks, chats. Default tickets and tasks.",
            },
            "replicate": {
                "type": "boolean",
                "description": "If true, create Slack List / JIRA cards. Default false (preview only).",
            },
            "limit": {"type": "integer", "description": "Max items per kind (default 50)."},
        },
    },
)


def _resolve_connector(ctx: ToolContext, args: dict[str, Any]):
    connector_id = str(args.get("connector_id") or "periskope").strip().lower()
    connector = get_connector(connector_id)
    if connector is None:
        return None, ToolResult.error(f"Unknown connector `{connector_id}`.")
    if not connector.enabled(ctx.config):
        return None, ToolResult.error(f"Connector `{connector_id}` is disabled. Enable it in Integrations.")
    return connector, None


def connector_list(_ctx: ToolContext, _args: dict[str, Any]) -> ToolResult:
    ids = list_connector_ids()
    return ToolResult(kind="connector_list", data={"connectors": ids})


def connector_list_chats(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    connector, error = _resolve_connector(ctx, args)
    if error:
        return error
    try:
        chats = connector.list_chats(ctx.config)
    except Exception as exc:
        return ToolResult.error(str(exc))
    return ToolResult(kind="connector_chats", data={"chats": chats[:80]})


def connector_list_tickets(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    connector, error = _resolve_connector(ctx, args)
    if error:
        return error
    limit = int(args.get("limit") or 30)
    try:
        tickets = connector.list_tickets(ctx.config, limit=max(1, min(limit, 100)))
    except Exception as exc:
        return ToolResult.error(str(exc))
    return ToolResult(
        kind="connector_tickets",
        data={"tickets": [item.to_dict() for item in tickets[:80]]},
    )


def connector_list_tasks(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    connector, error = _resolve_connector(ctx, args)
    if error:
        return error
    limit = int(args.get("limit") or 30)
    try:
        tasks = connector.list_tasks(ctx.config, limit=max(1, min(limit, 100)))
    except Exception as exc:
        return ToolResult.error(str(exc))
    return ToolResult(
        kind="connector_tasks",
        data={"tasks": [item.to_dict() for item in tasks[:80]]},
    )


def connector_get_messages(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    connector, error = _resolve_connector(ctx, args)
    if error:
        return error
    chat_id = str(args.get("chat_id") or "").strip()
    start_time = str(args.get("start_time") or "").strip()
    end_time = str(args.get("end_time") or "").strip()
    limit = int(args.get("limit") or 500)
    task = (ctx.extra or {}).get("current_task")
    intent = str(getattr(task, "cleaned_intent", "") or "") if task is not None else ""
    from backend.integrations.periskope.time_range import resolve_message_window

    start_time, end_time = resolve_message_window(start_time, end_time, intent=intent)
    try:
        messages = connector.list_messages(
            ctx.config,
            chat_id=chat_id,
            start_time=start_time,
            end_time=end_time,
            limit=max(1, min(limit, 500)),
            intent=intent,
        )
    except Exception as exc:
        return ToolResult.error(str(exc))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in messages:
        grouped.setdefault(str(item.get("chat_id") or chat_id or "unknown"), []).append(item)
    chats = [
        {
            "chat_id": cid,
            "message_count": len(items),
            "messages": items[:40],
        }
        for cid, items in grouped.items()
    ]
    return ToolResult(
        kind="connector_messages",
        data={
            "chat_id": chat_id or None,
            "start_time": start_time or None,
            "end_time": end_time or None,
            "message_count": len(messages),
            "chat_count": len(chats),
            "chats": chats[:80],
        },
    )


def connector_poll(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    connector, error = _resolve_connector(ctx, args)
    if error:
        return error
    if ctx.data_dir is None:
        return ToolResult.error("Alfred data directory is not available.")
    from backend.integrations.platform.poll import poll_connector

    kinds = args.get("kinds")
    if isinstance(kinds, str):
        kinds = [part.strip() for part in kinds.split(",") if part.strip()]
    try:
        result = poll_connector(
            connector.id,
            ctx.config,
            data_dir=ctx.data_dir,
            kinds=list(kinds) if isinstance(kinds, list) else None,
            replicate=bool(args.get("replicate")),
            limit=int(args.get("limit") or 50),
        )
    except Exception as exc:
        return ToolResult.error(str(exc))
    if not result.get("ok"):
        return ToolResult.error(str(result.get("error") or "Poll failed."))
    return ToolResult(kind="connector_poll", data=result)


def connector_tools() -> list[BaseTool]:
    return [
        FunctionTool(
            name="connector_list",
            capability="connector.read.list",
            operation="list",
            domain="connector",
            schema=CONNECTOR_LIST,
            run_fn=connector_list,
        ),
        FunctionTool(
            name="connector_list_chats",
            capability="connector.read.chats",
            operation="list_chats",
            domain="connector",
            schema=CONNECTOR_LIST_CHATS,
            run_fn=connector_list_chats,
        ),
        FunctionTool(
            name="connector_list_tickets",
            capability="connector.read.tickets",
            operation="list_tickets",
            domain="connector",
            schema=CONNECTOR_LIST_TICKETS,
            run_fn=connector_list_tickets,
        ),
        FunctionTool(
            name="connector_list_tasks",
            capability="connector.read.tasks",
            operation="list_tasks",
            domain="connector",
            schema=CONNECTOR_LIST_TASKS,
            run_fn=connector_list_tasks,
        ),
        FunctionTool(
            name="connector_get_messages",
            capability="connector.read.messages",
            operation="get_messages",
            domain="connector",
            schema=CONNECTOR_GET_MESSAGES,
            run_fn=connector_get_messages,
        ),
        FunctionTool(
            name="connector_poll",
            capability="connector.read.poll",
            operation="poll",
            domain="connector",
            schema=CONNECTOR_POLL,
            run_fn=connector_poll,
        ),
    ]
