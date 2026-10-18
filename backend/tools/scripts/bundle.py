"""Company script tool bundle."""

from __future__ import annotations

from backend.tools.base.bundle import ToolBundle
from backend.tools.base.tool import BaseTool
from backend.tools.scripts.tools import script_tools


class ScriptToolBundle(ToolBundle):
    capability_prefix = "script"

    def tools(self) -> list[BaseTool]:
        return script_tools()
