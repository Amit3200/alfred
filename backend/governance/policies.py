"""Channel, user, and source policies for write tools."""

from __future__ import annotations

from backend.models.config import AlfredConfig, GovernanceConfig
from backend.models.task import Task


def check_write_policy(
    tool_name: str,
    task: Task,
    config: AlfredConfig,
) -> str | None:
    """Return an error message if the write is blocked by policy, else None."""
    gov = config.governance
    if not gov.enabled:
        return None

    source = task.source
    if gov.write_allowed_sources and source not in gov.write_allowed_sources:
        return f"Write tool {tool_name!r} is not allowed from source {source!r}."

    if source in ("slack", "ui"):
        channel = (task.channel_id or "").strip()
        blocked = {c.lower() for c in gov.write_blocked_channels if c.strip()}
        if channel and channel.lower() in blocked:
            return f"Write tools are blocked in channel {channel!r}."

        allowed_channels = [c for c in gov.write_allowed_channels if c.strip()]
        if allowed_channels and channel:
            allowed_lower = {c.lower() for c in allowed_channels}
            if channel.lower() not in allowed_lower and "*" not in allowed_lower:
                return f"Write tools are not allowed in channel {channel!r}."

        allowed_users = [u for u in gov.write_allowed_users if u.strip()]
        if allowed_users:
            user = (task.user_id or "").strip()
            if user not in allowed_users:
                return f"User {user!r} is not authorized for write tools."

    return None
