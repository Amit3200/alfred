"""Repo context generation from shared git mirrors."""

from backend.context.doc_index import build_doc_index, doc_index_status, search_repo_docs
from backend.context.generator import (
    generate_repo_context,
    load_repo_context_for_prompt,
    read_context_manifest,
    resolve_main_repo,
)
from backend.context.graphify import extract_graph, graph_status, query_graph
from backend.context.suggestions import (
    approve_suggestion,
    dismiss_suggestion,
    generate_suggestions,
    list_pending_suggestions,
)

__all__ = [
    "approve_suggestion",
    "build_doc_index",
    "dismiss_suggestion",
    "doc_index_status",
    "extract_graph",
    "generate_repo_context",
    "generate_suggestions",
    "graph_status",
    "list_pending_suggestions",
    "load_repo_context_for_prompt",
    "query_graph",
    "read_context_manifest",
    "resolve_main_repo",
    "search_repo_docs",
]
