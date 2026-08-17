"""HTML artifact tool bundle."""

from __future__ import annotations

from backend.tools.artifacts.tools import artifact_tools
from backend.tools.base.bundle import ToolBundle
from backend.tools.base.tool import BaseTool


class ArtifactToolBundle(ToolBundle):
    capability_prefix = "artifact"

    def tools(self) -> list[BaseTool]:
        return artifact_tools()
