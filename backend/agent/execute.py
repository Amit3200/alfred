"""Shared tool execution for agent loops."""

from __future__ import annotations

import logging
from typing import Any

from backend.tools.base.logging import ToolExecutionLog
from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def execute_tool(
    registry: ToolRegistry,
    name: str,
    arguments: dict,
    *,
    allowed: list[str],
    session: Any | None = None,
    git: Any | None = None,
    task_id: str | None = None,
    session_key: str | None = None,
) -> str:
    from backend.observability.checkpoint import log_checkpoint

    operation = "write" if name.startswith(
        ("jira_", "google_", "git_", "transition_", "link_", "add_")
    ) and "read" not in name and name not in (
        "get_jira_issue",
        "google_read_sheet",
        "google_read_doc",
        "get_pr",
        "get_pr_changes",
        "list_",
    ) else "read"

    exec_log = ToolExecutionLog.start(
        tool_name=name,
        operation=operation,
        args=arguments,
        task_id=task_id,
        session_key=session_key,
    )

    checkpoint_name = f"{name}_tool_call"
    if name.startswith("jira") or name in (
        "add_jira_comment",
        "link_jira_issue",
        "get_jira_issue",
        "transition_jira_issue",
    ):
        checkpoint_name = "jira_tool_call"
    elif name.startswith("google"):
        checkpoint_name = "google_tool_call"
    elif name.startswith(("git", "github", "list_my_prs", "list_prs", "get_pr", "grep_repo", "read_file")):
        checkpoint_name = "git_tool_call"
    elif name.startswith(("athena", "cloudwatch")):
        checkpoint_name = "aws_tool_call"
    elif name.startswith("slack_"):
        checkpoint_name = "slack_tool_call"

    log_checkpoint(checkpoint_name, name, "started")
    try:
        git_cfg = git or getattr(registry, "git_config", None)
        if git_cfg is not None:
            result = registry.run_normalized(
                name,
                arguments,
                allowed=allowed,
                git=git_cfg,
                session=session,
            )
        else:
            result = registry.run(name, arguments, allowed=allowed)

        if result.kind == "error":
            message = str(result.data.get("message", "Tool execution error"))
            log_checkpoint(checkpoint_name, name, "error", error=RuntimeError(message))
            exec_log.finish(success=False, result_kind="error", error=message)
            observation = result.to_json()
            registry.record_trace(name, success=False, result_kind="error", observation=observation)
            return observation
        log_checkpoint(checkpoint_name, name, "completed")
        exec_log.finish(success=True, result_kind=result.kind)
        observation = result.to_json()
        registry.record_trace(name, success=True, result_kind=result.kind, observation=observation)
        return observation
    except Exception as exc:
        log_checkpoint(checkpoint_name, name, "error", error=exc)
        exec_log.finish(success=False, error=str(exc))
        logger.exception("Tool %s failed", name)
        raise
