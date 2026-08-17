"""Mandatory doc search/read before the doc Q&A agent loop."""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.ai.base import Message
from backend.agent.execute import execute_tool

logger = logging.getLogger(__name__)


def bootstrap_doc_qa(
    registry: Any,
    *,
    query: str,
    allowed: list[str],
    session: Any | None,
    git: Any,
    task_id: str | None = None,
    session_key: str | None = None,
) -> str:
    """Run search_repo_docs (+ read when matched). Returns context for the agent."""
    from backend.context.doc_index import (
        describe_missing_doc_topic,
        pick_best_doc_hit,
        significant_query_tokens,
    )

    stripped = (query or "").strip()
    if "search_repo_docs" not in allowed:
        return "Doc search tool is not available for this request."

    search_obs = execute_tool(
        registry,
        "search_repo_docs",
        {"query": stripped},
        allowed=allowed,
        session=session,
        git=git,
        task_id=task_id,
        session_key=session_key,
    )

    lines = [
        "## Documentation retrieval (already executed — do not skip)",
        f"Query: {stripped}",
        "",
        "### search_repo_docs",
        search_obs,
    ]

    try:
        parsed = json.loads(search_obs)
    except json.JSONDecodeError:
        parsed = {}

    payload = parsed.get("data") if isinstance(parsed.get("data"), dict) else parsed
    if parsed.get("kind") == "error":
        lines.append("\nDoc search failed — answer **No** or explain the search error.")
        return "\n".join(lines)

    entities = significant_query_tokens(stripped)
    hits = list(payload.get("results") or [])
    found = bool(payload.get("found"))
    best = pick_best_doc_hit(hits, stripped) if found and hits else None

    if best and "read_repo_doc" in allowed:
        from backend.observability.checkpoint import log_checkpoint

        read_args: dict[str, str] = {"path": str(best.get("path") or "")}
        repo = str(best.get("repo") or "").strip()
        log_checkpoint("doc_found", str(best.get("path") or ""), "completed")
        if repo:
            log_checkpoint("repo_context", repo, "completed")
            read_args["repo"] = repo
        if read_args["path"]:
            read_obs = execute_tool(
                registry,
                "read_repo_doc",
                read_args,
                allowed=allowed,
                session=session,
                git=git,
                task_id=task_id,
                session_key=session_key,
            )
            lines.extend(["", "### read_repo_doc", read_obs])
    elif entities and not best:
        topic = describe_missing_doc_topic(stripped)
        lines.append(
            f"\nNo indexed doc matched **{topic}**. "
            "Answer **No** — not documented in FlexyPe support docs."
        )
    elif not found:
        if entities:
            topic = describe_missing_doc_topic(stripped)
            lines.append(
                f"\nSearch found nothing for **{topic}**. "
                "Answer **No** — not documented."
            )
        else:
            lines.append("\nSearch returned no hits. Answer **No** or ask a clarifying question.")

    return "\n".join(lines)


def inject_doc_qa_bootstrap_message(
    messages: list[Message],
    registry: Any,
    *,
    query: str,
    allowed: list[str],
    session: Any | None,
    git: Any,
    task_id: str | None = None,
    session_key: str | None = None,
) -> list[Message]:
    """Append pre-fetched doc tool results so the agent summarizes grounded content."""
    bootstrap = bootstrap_doc_qa(
        registry,
        query=query,
        allowed=allowed,
        session=session,
        git=git,
        task_id=task_id,
        session_key=session_key,
    )
    out = list(messages)
    out.append(
        Message(
            role="user",
            content=(
                f"{bootstrap}\n\n"
                "Using ONLY the tool results above, write your final answer now. "
                "Start with **Yes** or **No**, cite doc paths from the results, "
                "and do not claim support without evidence in the search/read output."
            ),
        )
    )
    return out
