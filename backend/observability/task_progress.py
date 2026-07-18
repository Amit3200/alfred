"""Human-readable progress labels for in-flight chat tasks."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from backend.paths import db_path

TOOL_PROGRESS_LABELS: dict[str, str] = {
    "grep_repo": "Searching codebase",
    "read_file": "Reading source file",
    "git_log": "Reading git history",
    "git_blame": "Running git blame",
    "git_show": "Inspecting commit",
    "git_prepare_branch": "Preparing feature branch",
    "write_file": "Writing changes",
    "write_debug_script": "Writing debug script",
    "run_debug_script": "Running debug script",
    "git_commit": "Creating commit",
    "git_push_branch": "Pushing branch",
    "create_pull_request": "Opening pull request",
    "list_repos": "Listing repositories",
    "list_prs": "Listing pull requests",
    "list_my_prs": "Listing your pull requests",
    "get_pr": "Fetching pull request",
    "get_pr_changes": "Reading PR diff",
    "athena_query": "Querying Athena",
    "cloudwatch_query": "Querying CloudWatch logs",
    "list_cloudwatch_log_groups": "Listing log groups",
    "query_graph": "Querying code graph",
    "web_search": "Searching the web",
    "run_company_script": "Running company script",
}

CHECKPOINT_PROGRESS_LABELS: dict[str, str] = {
    "process_task": "Starting task",
    "agent_loop_start": "Analyzing request",
    "queue_task": "Queued",
}


def _tool_label(function_name: str) -> str:
    if function_name in TOOL_PROGRESS_LABELS:
        return TOOL_PROGRESS_LABELS[function_name]
    return function_name.replace("_", " ").strip()


def format_checkpoint_progress(checkpoint: str, function_name: str, status: str) -> str:
    if checkpoint.endswith("_tool_call") or function_name in TOOL_PROGRESS_LABELS:
        label = _tool_label(function_name)
        if status == "started":
            return f"{label}…"
        if status == "completed":
            return f"{label} — done"
        if status == "error":
            return f"{label} — failed"
        return label

    generic = CHECKPOINT_PROGRESS_LABELS.get(checkpoint) or CHECKPOINT_PROGRESS_LABELS.get(function_name)
    if generic:
        if status == "completed":
            return f"{generic} — done"
        if status == "error":
            return f"{generic} — failed"
        return f"{generic}…"

    if status == "error":
        return "Something went wrong"
    return "Thinking…"


def load_task_checkpoints(data_dir: Path | None, task_id: str) -> list[dict[str, Any]]:
    if not data_dir or not task_id:
        return []

    from backend.observability.checkpoint import init_checkpoint_db

    db_file = db_path(data_dir)
    init_checkpoint_db(db_file)
    conn = sqlite3.connect(db_file, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT checkpoint, function_name, status, timestamp
            FROM task_checkpoints
            WHERE task_id = ?
            ORDER BY id ASC
            """,
            (task_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def latest_task_progress(
    data_dir: Path | None,
    task_id: str,
    *,
    task_status: str | None = None,
) -> dict[str, Any]:
    """Return the latest user-visible progress for a background task."""
    checkpoints = load_task_checkpoints(data_dir, task_id)
    if not checkpoints:
        label = "Thinking…"
        if task_status == "pending":
            label = "Queued…"
        return {
            "progress_label": label,
            "current_tool": None,
            "recent_tools": [],
        }

    last = checkpoints[-1]
    label = format_checkpoint_progress(
        str(last.get("checkpoint") or ""),
        str(last.get("function_name") or ""),
        str(last.get("status") or ""),
    )

    if task_status in ("pending", "running") and last.get("status") == "completed":
        if str(last.get("checkpoint") or "").endswith("_tool_call"):
            label = "Planning next step…"

    recent_tools: list[str] = []
    for row in checkpoints:
        fn = str(row.get("function_name") or "")
        if str(row.get("checkpoint") or "").endswith("_tool_call") and row.get("status") == "completed":
            if fn and (not recent_tools or recent_tools[-1] != fn):
                recent_tools.append(fn)
    recent_tools = recent_tools[-4:]

    current_tool = None
    if str(last.get("checkpoint") or "").endswith("_tool_call") and last.get("status") == "started":
        current_tool = str(last.get("function_name") or "") or None

    return {
        "progress_label": label,
        "current_tool": current_tool,
        "recent_tools": recent_tools,
    }
