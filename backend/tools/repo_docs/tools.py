"""Repo documentation tools."""

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
from backend.context.doc_urls import attach_public_doc_urls, public_doc_url
from backend.context.generator import resolve_main_repo
from backend.context.repo_profiles import (
    doc_search_repo_slugs,
    docs_only_query,
    knowledge_doc_repo_slugs,
    normalize_repo_slug,
)
from backend.routing.chat_persona import doc_search_scope_for_persona, persona_from_interaction_context
from backend.tools.base.function_tool import FunctionTool
from backend.tools.base.tool import BaseTool, ToolContext
from backend.tools.repo_docs.schemas import LIST_REPO_DOCS, READ_REPO_DOC, SEARCH_REPO_DOCS
from backend.tools.result import ToolResult


def _data_path(ctx: ToolContext) -> Path | ToolResult:
    if ctx.data_dir is None:
        return ToolResult.error("data_dir is required for repo doc tools.")
    return ctx.data_dir


def _resolve_repo(ctx: ToolContext, raw: str | None) -> str | None:
    text = (raw or "").strip()
    if text:
        return normalize_repo_slug(text, ctx.config.git)
    return resolve_main_repo(ctx.config.git)


def search_repo_docs_tool(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    data_path = _data_path(ctx)
    if isinstance(data_path, ToolResult):
        return data_path
    config = ctx.config
    query = str(args.get("query") or "").strip()
    if not query:
        return ToolResult.error("query is required")
    limit = min(int(args.get("limit") or config.repo_knowledge.max_search_results), 20)
    repo_arg = str(args.get("repo") or "").strip()
    if repo_arg:
        slug = _resolve_repo(ctx, repo_arg)
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
    hits = attach_public_doc_urls(hits, config=config)
    return ToolResult(
        kind="doc_search",
        data={"query": query, "results": hits, "found": True, "count": len(hits)},
    )


def read_repo_doc_tool(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    data_path = _data_path(ctx)
    if isinstance(data_path, ToolResult):
        return data_path
    slug = _resolve_repo(ctx, str(args.get("repo") or ""))
    if not slug:
        return ToolResult.error("repo is not configured")
    path = str(args.get("path") or "").strip()
    if not path:
        return ToolResult.error("path is required")
    try:
        doc = read_indexed_doc(
            data_path,
            ctx.config.git,
            slug,
            path,
            max_chars=ctx.config.repo_knowledge.max_read_chars,
        )
    except FileNotFoundError as exc:
        return ToolResult.error(str(exc))
    except ValueError as exc:
        return ToolResult.error(str(exc))
    doc["repo"] = slug
    url = public_doc_url(path, repo=slug, config=ctx.config)
    if url:
        doc["url"] = url
    return ToolResult(kind="doc_content", data=doc)


def list_repo_docs_tool(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    data_path = _data_path(ctx)
    if isinstance(data_path, ToolResult):
        return data_path
    slug = _resolve_repo(ctx, str(args.get("repo") or ""))
    if not slug:
        return ToolResult.error("repo is not configured")
    docs = list_indexed_docs(data_path, slug)
    prefix = str(args.get("prefix") or "").strip().lower()
    if prefix:
        docs = [d for d in docs if d["path"].lower().startswith(prefix)]
    docs = attach_public_doc_urls(docs, repo=slug, config=ctx.config)
    return ToolResult(kind="doc_list", data={"repo": slug, "docs": docs, "count": len(docs)})


def repo_doc_tools() -> list[BaseTool]:
    return [
        FunctionTool(
            name="search_repo_docs",
            capability="repo.docs.qa",
            operation="search",
            domain="repo_docs",
            schema=SEARCH_REPO_DOCS,
            run_fn=search_repo_docs_tool,
            produces=("doc_hits",),
            next_tools=("read_repo_doc",),
        ),
        FunctionTool(
            name="read_repo_doc",
            capability="repo.docs.qa",
            operation="read",
            domain="repo_docs",
            schema=READ_REPO_DOC,
            run_fn=read_repo_doc_tool,
            consumes=("doc_hits",),
            produces=("doc_content",),
        ),
        FunctionTool(
            name="list_repo_docs",
            capability="repo.docs.qa",
            operation="list",
            domain="repo_docs",
            schema=LIST_REPO_DOCS,
            run_fn=list_repo_docs_tool,
            produces=("doc_list",),
            next_tools=("read_repo_doc",),
        ),
    ]
