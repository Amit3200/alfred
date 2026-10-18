"""Git tool bundles."""

from __future__ import annotations

from backend.tools.base.bundle import ToolBundle
from backend.tools.base.tool import BaseTool
from backend.tools.git.api import git_api_tools
from backend.tools.git.graphify import graphify_tools
from backend.tools.git.local import git_local_tools
from backend.tools.git.write import git_write_tools


class GitApiToolBundle(ToolBundle):
    capability_prefix = "git.pr"

    def tools(self) -> list[BaseTool]:
        return git_api_tools()


class GitLocalToolBundle(ToolBundle):
    capability_prefix = "git.repo"

    def tools(self) -> list[BaseTool]:
        return git_local_tools()


class GitWriteToolBundle(ToolBundle):
    capability_prefix = "git.write"

    def tools(self) -> list[BaseTool]:
        return git_write_tools()


class GraphifyToolBundle(ToolBundle):
    capability_prefix = "git.repo"

    def tools(self) -> list[BaseTool]:
        return graphify_tools()
