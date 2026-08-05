"""Domain-scoped subagent execution for multi-step tool plans."""

from __future__ import annotations

import logging
from typing import Any

from backend.routing.tool_plan_types import ToolPlan, ToolPlanStep
from backend.tools.catalog import tool_domain

logger = logging.getLogger(__name__)

_DOMAIN_WORKERS = {
    "jira": "jira_worker",
    "google_sheet": "google_worker",
    "google_doc": "google_worker",
    "slack": "slack_worker",
    "git": "git_worker",
    "git_write": "git_worker",
    "aws": "aws_worker",
}


def should_use_subagents(plan: ToolPlan | None) -> bool:
    """Use sequential domain workers when plan spans multiple domains with 3+ steps."""
    if plan is None or len(plan.tools_needed) < 3:
        return False
    domains = {tool_domain(t) for t in plan.tools_needed}
    domains.discard("other")
    return len(domains) >= 2


def group_steps_by_domain(steps: list[ToolPlanStep]) -> list[tuple[str, list[ToolPlanStep]]]:
    groups: list[tuple[str, list[ToolPlanStep]]] = []
    current_domain = ""
    bucket: list[ToolPlanStep] = []
    for step in steps:
        domain = tool_domain(step.tool)
        if domain != current_domain:
            if bucket:
                groups.append((current_domain, bucket))
            current_domain = domain
            bucket = [step]
        else:
            bucket.append(step)
    if bucket:
        groups.append((current_domain, bucket))
    return groups


def worker_name_for_domain(domain: str) -> str:
    return _DOMAIN_WORKERS.get(domain, "general_worker")


def build_subagent_manifest(domain: str, steps: list[ToolPlanStep]) -> str:
    worker = worker_name_for_domain(domain)
    tool_lines = "\n".join(f"- `{step.tool}` — {step.purpose or 'required step'}" for step in steps)
    return (
        f"## Subagent: {worker}\n"
        f"Domain: `{domain}`\n"
        f"Execute ONLY these tools in order:\n{tool_lines}\n"
        "Return structured results; do not invent URLs or issue keys."
    )


def scoped_tools_for_domain(steps: list[ToolPlanStep], allowed: list[str]) -> list[str]:
    needed = [step.tool for step in steps]
    allowed_set = set(allowed)
    scoped = [tool for tool in needed if tool in allowed_set]
    if scoped:
        return scoped
    return [tool for tool in needed if tool in allowed_set or not allowed]
