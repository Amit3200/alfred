"""Schedule tool bundle."""

from __future__ import annotations

from backend.tools.base.bundle import ToolBundle
from backend.tools.base.tool import BaseTool
from backend.tools.schedule.tools import schedule_tools


class ScheduleToolBundle(ToolBundle):
    capability_prefix = "schedule"

    def tools(self) -> list[BaseTool]:
        return schedule_tools()
