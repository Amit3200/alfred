"""Repo documentation tool bundle."""

from __future__ import annotations

from backend.tools.base.bundle import ToolBundle
from backend.tools.base.tool import BaseTool
from backend.tools.repo_docs.tools import repo_doc_tools


class RepoDocsToolBundle(ToolBundle):
    capability_prefix = "repo.docs"

    def tools(self) -> list[BaseTool]:
        return repo_doc_tools()
