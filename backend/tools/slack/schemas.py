"""Slack read tool schemas."""

from __future__ import annotations

from backend.ai.base import ToolSchema

SLACK_FETCH_THREAD = ToolSchema(
    name="slack_fetch_thread",
    description=(
        "Fetch Slack thread messages for the current task channel/thread. "
        "Use before summarizing a thread — returns structured message text."
    ),
    parameters={
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Max messages to fetch (default 50, max 100).",
            },
        },
        "required": [],
    },
)

SLACK_FETCH_CHANNEL_HISTORY = ToolSchema(
    name="slack_fetch_channel_history",
    description=(
        "Fetch Slack channel message history for a time window inferred from the user query "
        "(e.g. last 7 days, yesterday). Use before summarizing alerts or bugs."
    ),
    parameters={
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Optional override: number of days of history (max 90).",
            },
            "limit": {
                "type": "integer",
                "description": "Max messages (default 200).",
            },
        },
        "required": [],
    },
)

SLACK_TOOL_NAMES = frozenset({"slack_fetch_thread", "slack_fetch_channel_history"})
