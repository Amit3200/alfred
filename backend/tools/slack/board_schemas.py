"""Slack List board management tool schemas."""

from __future__ import annotations

from backend.ai.base import ToolSchema

SLACK_BOARD_CREATE_TASK = ToolSchema(
    name="slack_board_create_task",
    description=(
        "Create a task on the configured Slack List board for this channel. "
        "Use after fetching thread context when the user asks to create a task from the conversation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Task title / issue name."},
            "description": {"type": "string", "description": "Details from thread or user."},
            "severity": {"type": "string", "description": "High, Medium, or Low."},
            "merchant": {"type": "string", "description": "Merchant name if known."},
            "assignee_user_id": {"type": "string", "description": "Slack user id to assign."},
        },
        "required": ["title"],
    },
)

SLACK_BOARD_UPDATE_TASK = ToolSchema(
    name="slack_board_update_task",
    description="Update status, assignee, or severity on a Slack List task by display id or record id.",
    parameters={
        "type": "object",
        "properties": {
            "ticket_ref": {"type": "string", "description": "TS-123 or Rec… id."},
            "status": {"type": "string", "description": "Not picked, In progress, Review, Done."},
            "assignee_user_id": {"type": "string", "description": "Slack user id."},
            "severity": {"type": "string", "description": "High, Medium, Low."},
        },
        "required": ["ticket_ref"],
    },
)

SLACK_BOARD_SEARCH_TASKS = ToolSchema(
    name="slack_board_search_tasks",
    description="Search/list tasks on the channel's Slack List board.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Text to match in title/fields."},
            "status": {"type": "string", "description": "Filter by status label."},
            "limit": {"type": "integer", "description": "Max results (default 20)."},
        },
        "required": [],
    },
)

SLACK_BOARD_GET_TASK = ToolSchema(
    name="slack_board_get_task",
    description="Get full details for one Slack List task.",
    parameters={
        "type": "object",
        "properties": {
            "ticket_ref": {"type": "string", "description": "TS-123 or Rec… id."},
        },
        "required": ["ticket_ref"],
    },
)

SLACK_BOARD_COMMENT = ToolSchema(
    name="slack_board_comment",
    description="Post a comment in the Slack thread linked to a board task.",
    parameters={
        "type": "object",
        "properties": {
            "ticket_ref": {"type": "string", "description": "TS-123 or Rec… id."},
            "text": {"type": "string", "description": "Comment text."},
        },
        "required": ["ticket_ref", "text"],
    },
)

SLACK_BOARD_TOOL_NAMES = frozenset(
    {
        "slack_board_create_task",
        "slack_board_update_task",
        "slack_board_search_tasks",
        "slack_board_get_task",
        "slack_board_comment",
    }
)
