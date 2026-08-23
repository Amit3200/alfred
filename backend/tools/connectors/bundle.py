"""Connector read tool bundle."""

from __future__ import annotations

from backend.tools.base.bundle import ToolBundle
from backend.tools.base.tool import BaseTool
from backend.tools.connectors.tools import connector_tools


class ConnectorToolBundle(ToolBundle):
    capability_prefix = "connector.read"

    def tools(self) -> list[BaseTool]:
        return connector_tools()
