"""Register Slack read class tools."""

from __future__ import annotations

from backend.models.config import AlfredConfig
from backend.models.task import Task
from backend.tools.base.bundle import ToolBundle
from backend.tools.base.tool import BaseTool
from backend.tools.registry import ToolRegistry
from backend.tools.slack.read_tools import slack_read_tools


class SlackReadToolBundle(ToolBundle):
    capability_prefix = "slack.read"

    def tools(self) -> list[BaseTool]:
        return slack_read_tools()


def register_slack_tools(
    registry: ToolRegistry,
    config: AlfredConfig,
    *,
    default_task: Task | None = None,
) -> None:
    if not config.slack.enabled:
        return
    token = (config.slack.bot_token or "").strip()
    if not token:
        return
    registry.alfred_config = config
    extra = {"default_task": default_task} if default_task is not None else None
    SlackReadToolBundle().register(registry, extra=extra)
