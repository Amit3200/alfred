"""Repo documentation search and read tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.context.doc_index import (
    list_indexed_docs,
    pick_best_doc_hit,
    read_indexed_doc,
    search_all_repo_docs,
    search_repo_docs,
    significant_query_tokens,
)
from backend.context.generator import resolve_main_repo
from backend.context.repo_profiles import (
    doc_search_repo_slugs,
    docs_only_query,
    knowledge_doc_repo_slugs,
    normalize_repo_slug,
)
from backend.models.config import AlfredConfig
from backend.routing.chat_persona import doc_search_scope_for_persona, persona_from_interaction_context
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

    def _resolve_repo(raw: str | None) -> str | None:
        text = (raw or "").strip()
        if text:
            return normalize_repo_slug(text, config.git)
        return resolve_main_repo(config.git)

    def search_handler(args: dict[str, Any]) -> ToolResult:
        query = str(args.get("query") or "").strip()
        if not query:
            return ToolResult.error("query is required")
        limit = min(int(args.get("limit") or config.repo_knowledge.max_search_results), 20)
        repo_arg = str(args.get("repo") or "").strip()
        if repo_arg:
            slug = _resolve_repo(repo_arg)
            if not slug:
                return ToolResult.error("repo is not configured")
            hits = search_repo_docs(data_path, slug, query, limit=limit)
            for hit in hits:
                hit["repo"] = slug
        else:
            slugs = doc_search_repo_slugs(config, data_path)
            persona = persona_from_interaction_context()
            exclude: tuple[str, ...] = ()
            include_only: tuple[str, ...] = ()
            if persona is not None:
                slugs, exclude, include_only = doc_search_scope_for_persona(
                    config,
                    data_path,
                    persona,
                    query,
                    default_slugs=slugs,
                )
            elif docs_only_query(query):
                docs_only = knowledge_doc_repo_slugs(config, data_path)
                if docs_only:
                    slugs = docs_only
                    exclude = ("playbooks/",)
            if not slugs:
                return ToolResult.error("No indexed documentation repositories")
            if not exclude and not include_only:
                lower = query.lower()
                if not any(token in lower for token in ("playbook", "runbook", "investigate")):
                    exclude = ("playbooks/",)
            hits = search_all_repo_docs(
                data_path,
                slugs,
                query,
                limit=limit,
                exclude_path_prefixes=exclude,
            )
            if include_only:
                hits = [
                    hit
                    for hit in hits
                    if any(str(hit.get("path") or "").startswith(prefix) for prefix in include_only)
                ]
            best = pick_best_doc_hit(hits, query)
            if best:
                hits = [best, *[h for h in hits if h is not best]]
            elif hits and significant_query_tokens(query):
                return ToolResult(
                    kind="doc_search",
                    data={"query": query, "results": [], "found": False},
                )
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
        slug = _resolve_repo(str(args.get("repo") or ""))
        if not slug:
            return ToolResult.error("repo is not configured")
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
        doc["repo"] = slug
        return ToolResult(kind="doc_content", data=doc)

    def list_handler(args: dict[str, Any]) -> ToolResult:
        slug = _resolve_repo(str(args.get("repo") or ""))
        if not slug:
            return ToolResult.error("repo is not configured")
        docs = list_indexed_docs(data_path, slug)
        prefix = str(args.get("prefix") or "").strip().lower()
        if prefix:
            docs = [d for d in docs if d["path"].lower().startswith(prefix)]
        return ToolResult(kind="doc_list", data={"repo": slug, "docs": docs, "count": len(docs)})

    registry.register(SEARCH_REPO_DOCS, search_handler)
    registry.register(READ_REPO_DOC, read_handler)
    registry.register(LIST_REPO_DOCS, list_handler)
