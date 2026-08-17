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
    "search_repo_docs": "Searching documentation",
    "read_repo_doc": "Reading documentation",
    "list_repo_docs": "Listing documentation",
}

INTENT_PROGRESS_LABELS: dict[str, str] = {
    "repo.docs.qa": "Documentation Q&A",
    "slack.board.create": "Slack board task",
    "slack.board.update": "Update board task",
    "slack.board.search": "Search board tasks",
    "repo.code.search": "Code search",
    "repo.code.read": "Read source file",
    "git.pr.list": "List pull requests",
    "git.pr.review": "Review pull request",
    "general.chat": "General chat",
}

CHECKPOINT_PROGRESS_LABELS: dict[str, str] = {
    "process_task": "Starting task",
    "agent_loop_start": "Composing answer",
    "queue_task": "Queued",
    "route_plan": "Routing to documentation",
    "doc_synthesis": "Analyzing and summarizing",
    "doc_bootstrap": "Loading documentation",
    "board_bootstrap": "Creating board task",
    "graph_route": "Choosing execution path",
    "grounding": "Verifying answer",
}


def _tool_label(function_name: str) -> str:
    if function_name in TOOL_PROGRESS_LABELS:
        return TOOL_PROGRESS_LABELS[function_name]
    return function_name.replace("_", " ").strip()


def _intent_label(intent_class: str) -> str:
    if not intent_class:
        return ""
    return INTENT_PROGRESS_LABELS.get(intent_class, intent_class.replace(".", " · "))


def extract_progress_plan(checkpoints: list[dict[str, Any]]) -> dict[str, Any] | None:
    intent = ""
    goal = ""
    steps: list[str] = []
    for row in checkpoints:
        checkpoint = str(row.get("checkpoint") or "")
        function_name = str(row.get("function_name") or "")
        status = str(row.get("status") or "")
        if checkpoint == "tool_plan" and status == "completed" and function_name:
            intent = function_name
        elif checkpoint == "tool_plan_goal" and status == "completed" and function_name:
            goal = function_name
        elif checkpoint == "tool_plan_steps" and status == "completed" and function_name:
            steps = [part.strip() for part in function_name.split("→") if part.strip()]
    if not intent and not goal and not steps:
        return None
    return {
        "intent": intent,
        "intent_label": _intent_label(intent),
        "goal": goal,
        "steps": steps,
    }


def format_checkpoint_progress(checkpoint: str, function_name: str, status: str) -> str:
    if checkpoint == "route_plan" and function_name == "repo_knowledge":
        if status == "completed":
            return "Matched documentation question"
        return "Routing to documentation…"

    if checkpoint == "tool_plan" and status == "completed":
        return f"Plan: {_intent_label(function_name)}"

    if checkpoint == "graph_route" and status == "completed":
        if function_name == "worker":
            return "Investigating with agent…"
        if function_name == "direct":
            return "Answering directly…"
        return "Planning execution…"

    if checkpoint == "doc_bootstrap":
        if status == "completed":
            return "Documentation loaded — composing answer…"
        return "Searching documentation…"

    if checkpoint == "grounding":
        if status == "completed":
            return "Answer verified"
        if status == "error":
            return "Answer verification failed"
        return "Verifying answer…"

    if checkpoint == "doc_found" and function_name:
        if status == "error":
            return "Documentation lookup failed"
        return f"Found `{function_name}`"

    if checkpoint == "repo_context" and function_name:
        if status == "error":
            return f"Knowledge base `{function_name}` unavailable"
        return f"Using `{function_name}` knowledge base"

    if checkpoint == "doc_synthesis":
        label = CHECKPOINT_PROGRESS_LABELS.get("doc_synthesis", "Analyzing and summarizing")
        if status == "completed":
            return f"{label} — done"
        if status == "error":
            return f"{label} — failed"
        return f"{label}…"

    if checkpoint.endswith("_tool_call") or function_name in TOOL_PROGRESS_LABELS:
        label = _tool_label(function_name)
        if status == "started":
            return f"{label}…"
        if status == "completed":
            return f"{label} — done"
        if status == "error":
            return f"{label} — failed"
        return label

    if checkpoint.endswith("_loop_start"):
        label = CHECKPOINT_PROGRESS_LABELS.get("agent_loop_start", "Composing answer")
        if status == "completed":
            return f"{label} — done"
        return f"{label}…"

    if checkpoint.endswith("_loop_iteration") and "_final_answer" in function_name:
        return "Drafting answer…"

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


def _timeline_step_status(status: str) -> str:
    if status == "error":
        return "error"
    if status in ("completed", "cancelled"):
        return "done"
    return "active"


def _append_timeline_step(timeline: list[dict[str, str]], label: str, status: str) -> None:
    step_status = _timeline_step_status(status)
    if timeline and timeline[-1]["label"] == label:
        timeline[-1]["status"] = step_status
        return
    timeline.append({"label": label, "status": step_status})


def build_progress_timeline(
    checkpoints: list[dict[str, Any]],
    *,
    task_status: str | None = None,
) -> list[dict[str, str]]:
    """Build ordered user-visible progress steps for chat UI."""
    timeline: list[dict[str, str]] = []
    for row in checkpoints:
        checkpoint = str(row.get("checkpoint") or "")
        function_name = str(row.get("function_name") or "")
        status = str(row.get("status") or "")

        if checkpoint == "queue_task":
            continue

        label: str | None = None
        if checkpoint == "process_task" and status == "started":
            label = "Understanding your question"
        elif checkpoint == "tool_plan" and status == "completed":
            label = f"Plan: {_intent_label(function_name)}"
        elif checkpoint == "route_plan" and function_name == "repo_knowledge" and status == "completed":
            label = "Matched documentation question"
        elif checkpoint == "graph_route" and status == "completed" and function_name == "worker":
            label = "Investigating with agent"
        elif checkpoint == "doc_bootstrap" and status == "started":
            label = "Searching documentation"
        elif checkpoint == "doc_bootstrap" and status == "completed":
            label = "Documentation loaded"
        elif (
            checkpoint in ("doc_tool_call", "search_repo_docs_tool_call")
            and function_name == "search_repo_docs"
            and status == "started"
        ):
            label = "Searching documentation"
        elif checkpoint == "doc_found" and function_name:
            label = f"Found `{function_name}`"
        elif checkpoint == "repo_context" and function_name:
            label = f"Using `{function_name}` knowledge base"
        elif (
            checkpoint in ("doc_tool_call", "read_repo_doc_tool_call")
            and function_name == "read_repo_doc"
            and status == "started"
        ):
            label = "Reading documentation"
        elif checkpoint == "doc_synthesis" and function_name == "summarize" and status == "started":
            label = "Analyzing and summarizing"
        elif checkpoint == "agent_loop_start" and status == "started":
            label = "Composing answer"
        elif checkpoint.endswith("_loop_start") and status == "started":
            label = "Composing answer"
        elif checkpoint == "grounding" and status == "started":
            label = "Verifying answer"
        elif checkpoint == "grounding" and status == "completed":
            label = "Answer verified"
        elif checkpoint == "grounding" and status == "error":
            label = "Answer verification failed"
        elif checkpoint.endswith("_tool_call") and status == "started":
            label = _tool_label(function_name)

        if label is None:
            continue
        _append_timeline_step(timeline, label, status)

    if task_status in ("pending", "running") and timeline:
        last_row = checkpoints[-1] if checkpoints else {}
        last_status = str(last_row.get("status") or "")
        if last_status == "started":
            timeline[-1]["status"] = "active"
        elif last_status == "completed" and timeline[-1]["status"] != "error":
            timeline[-1]["status"] = "done"

    return timeline[-10:]


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
            "progress_steps": [{"label": "Understanding your question", "status": "active"}],
            "progress_plan": None,
        }

    last = checkpoints[-1]
    label = format_checkpoint_progress(
        str(last.get("checkpoint") or ""),
        str(last.get("function_name") or ""),
        str(last.get("status") or ""),
    )

    if task_status in ("pending", "running") and last.get("status") == "completed":
        last_checkpoint = str(last.get("checkpoint") or "")
        if last_checkpoint == "doc_bootstrap":
            label = "Composing answer…"
        elif last_checkpoint.endswith("_tool_call"):
            label = "Planning next step…"

    recent_tools: list[str] = []
    for row in checkpoints:
        fn = str(row.get("function_name") or "")
        if str(row.get("checkpoint") or "").endswith("_tool_call") and row.get("status") == "completed":
            if fn and (not recent_tools or recent_tools[-1] != fn):
                recent_tools.append(_tool_label(fn))
    recent_tools = recent_tools[-4:]

    current_tool = None
    if str(last.get("checkpoint") or "").endswith("_tool_call") and last.get("status") == "started":
        fn = str(last.get("function_name") or "")
        current_tool = _tool_label(fn) if fn else None

    progress_steps = build_progress_timeline(checkpoints, task_status=task_status)
    if not progress_steps and task_status in ("pending", "running"):
        progress_steps = [{"label": label.rstrip("…"), "status": "active"}]

    return {
        "progress_label": label,
        "current_tool": current_tool,
        "recent_tools": recent_tools,
        "progress_steps": progress_steps,
        "progress_plan": extract_progress_plan(checkpoints),
    }
