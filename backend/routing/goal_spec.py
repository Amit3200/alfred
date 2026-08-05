"""GoalSpec — machine-readable success criteria from a tool plan."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.routing.tool_plan_types import ToolPlan
from backend.tools.catalog import tool_domain

_WRITE_VERBS = re.compile(
    r"\b(create|created|assign|assigned|update|updated|move|moved|transition|"
    r"write|wrote|post|posted|add|added|link|linked)\b",
    re.I,
)

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)


@dataclass
class GoalSpec:
    intent_class: str
    goal: str
    required_tools: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    failure_response: str = "I couldn't complete that request with the available tools."
    requires_write: bool = False

    @property
    def domains(self) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for tool in self.required_tools:
            domain = tool_domain(tool)
            if domain not in seen:
                seen.add(domain)
                ordered.append(domain)
        return ordered


def goal_spec_from_plan(plan: ToolPlan | None) -> GoalSpec | None:
    if plan is None or not plan.tools_needed:
        return None

    write_domains = {"jira", "google_sheet", "google_doc", "git_write", "slack_write"}
    requires_write = any(tool_domain(t) in write_domains for t in plan.tools_needed)

    criteria = [f"Execute tools: {', '.join(plan.tools_needed)}"]
    if plan.intent_class.startswith("google.create"):
        criteria.append("Reply includes spreadsheet or document URL from tool result")
    if plan.intent_class.startswith("jira."):
        criteria.append("Reply references JIRA issue key or URL from tool result")
    if plan.intent_class.startswith("slack.summarize"):
        criteria.append("Summary based on fetched Slack messages, not invented content")

    failure = plan.goal
    if plan.missing_capabilities:
        failure = (
            f"I can't complete this yet — missing tools: {', '.join(plan.missing_capabilities)}."
        )

    return GoalSpec(
        intent_class=plan.intent_class or "unknown",
        goal=plan.goal,
        required_tools=list(plan.tools_needed),
        success_criteria=criteria,
        failure_response=failure,
        requires_write=requires_write,
    )


def extract_urls(text: str) -> set[str]:
    return {match.group(0).rstrip(".,)") for match in _URL_RE.finditer(text or "")}


def detect_action_claims(text: str) -> list[str]:
    return list({m.group(1).lower() for m in _WRITE_VERBS.finditer(text or "")})
