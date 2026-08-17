"""Web search tool bundle."""

from __future__ import annotations

from backend.tools.base.bundle import ToolBundle
from backend.tools.base.tool import BaseTool
from backend.tools.web.tools import web_tools


class WebToolBundle(ToolBundle):
    capability_prefix = "web"

    def tools(self) -> list[BaseTool]:
        return web_tools()
