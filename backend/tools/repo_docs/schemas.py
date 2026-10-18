"""Repo documentation tool schemas."""

from __future__ import annotations

from backend.ai.base import ToolSchema

SEARCH_REPO_DOCS = ToolSchema(
    name="search_repo_docs",
    description=(
        "Search indexed repository documentation and runbooks (BM25). "
        "Use before answering doc/runbook questions — returns cited excerpts and a public `url` "
        "when the repo has `docs_public_base_url` configured. "
        "Searches all configured doc repos when repo is omitted."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language search query.",
            },
            "repo": {
                "type": "string",
                "description": "Optional repo slug (e.g. Acme/docs). Defaults to all indexed doc repos.",
            },
            "limit": {
                "type": "integer",
                "description": "Max results (default from config, max 20).",
            },
        },
        "required": ["query"],
    },
)

READ_REPO_DOC = ToolSchema(
    name="read_repo_doc",
    description="Read full text of an indexed documentation file by path.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Doc path from search results or list_repo_docs.",
            },
            "repo": {
                "type": "string",
                "description": "Repository slug (defaults to git.main_repo).",
            },
        },
        "required": ["path"],
    },
)

LIST_REPO_DOCS = ToolSchema(
    name="list_repo_docs",
    description="List indexed documentation paths for a repository.",
    parameters={
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository slug (defaults to git.main_repo).",
            },
            "prefix": {
                "type": "string",
                "description": "Optional path prefix filter, e.g. docs/runbooks",
            },
        },
        "required": [],
    },
)

REPO_DOC_TOOL_NAMES = frozenset(
    {SEARCH_REPO_DOCS.name, READ_REPO_DOC.name, LIST_REPO_DOCS.name}
)
