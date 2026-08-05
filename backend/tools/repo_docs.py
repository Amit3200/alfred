"""Repo documentation search and read tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.context.doc_index import (
    list_indexed_docs,
    read_indexed_doc,
    search_repo_docs,
)
from backend.context.generator import resolve_main_repo
from backend.models.config import AlfredConfig
from backend.tools.registry import ToolRegistry
from backend.tools.repo_docs_schemas import LIST_REPO_DOCS, READ_REPO_DOC, SEARCH_REPO_DOCS
from backend.tools.result import ToolResult

REPO_DOC_TOOL_NAMES = frozenset({SEARCH_REPO_DOCS.name, READ_REPO_DOC.name, LIST_REPO_DOCS.name})


def register_repo_doc_tools(
    registry: ToolRegistry,
    config: AlfredConfig,
    *,
    data_dir: Any,
) -> None:
    if not config.repo_knowledge.enabled or not config.git.enabled:
        return

    data_path = Path(data_dir)

    def _repo_slug() -> str | None:
        return resolve_main_repo(config.git)

    def search_handler(args: dict[str, Any]) -> ToolResult:
        slug = _repo_slug()
        if not slug:
            return ToolResult.error("main_repo is not configured")
        query = str(args.get("query") or "").strip()
        if not query:
            return ToolResult.error("query is required")
        limit = min(int(args.get("limit") or config.repo_knowledge.max_search_results), 20)
        hits = search_repo_docs(data_path, slug, query, limit=limit)
        if not hits:
            return ToolResult(
                kind="doc_search",
                data={"query": query, "results": [], "found": False},
            )
        return ToolResult(
            kind="doc_search",
            data={"query": query, "results": hits, "found": True, "count": len(hits)},
        )

    def read_handler(args: dict[str, Any]) -> ToolResult:
        slug = _repo_slug()
        if not slug:
            return ToolResult.error("main_repo is not configured")
        path = str(args.get("path") or "").strip()
        if not path:
            return ToolResult.error("path is required")
        try:
            doc = read_indexed_doc(
                data_path,
                config.git,
                slug,
                path,
                max_chars=config.repo_knowledge.max_read_chars,
            )
        except FileNotFoundError as exc:
            return ToolResult.error(str(exc))
        except ValueError as exc:
            return ToolResult.error(str(exc))
        return ToolResult(kind="doc_content", data=doc)

    def list_handler(args: dict[str, Any]) -> ToolResult:
        slug = _repo_slug()
        if not slug:
            return ToolResult.error("main_repo is not configured")
        docs = list_indexed_docs(data_path, slug)
        prefix = str(args.get("prefix") or "").strip().lower()
        if prefix:
            docs = [d for d in docs if d["path"].lower().startswith(prefix)]
        return ToolResult(kind="doc_list", data={"docs": docs, "count": len(docs)})

    registry.register(SEARCH_REPO_DOCS, search_handler)
    registry.register(READ_REPO_DOC, read_handler)
    registry.register(LIST_REPO_DOCS, list_handler)
