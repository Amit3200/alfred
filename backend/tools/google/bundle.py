"""Google Workspace tool bundles."""

from __future__ import annotations

from backend.tools.base.bundle import ToolBundle
from backend.tools.base.tool import BaseTool
from backend.tools.google.docs.tools import doc_tools
from backend.tools.google.sheets.tools import sheet_tools


class GoogleSheetToolBundle(ToolBundle):
    capability_prefix = "google.sheet"

    def tools(self) -> list[BaseTool]:
        return sheet_tools()


class GoogleDocToolBundle(ToolBundle):
    capability_prefix = "google.doc"

    def tools(self) -> list[BaseTool]:
        return doc_tools()
