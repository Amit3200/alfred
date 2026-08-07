"""Map tool plans to governance skill policies."""

from __future__ import annotations

from pathlib import Path

from backend.routing.capabilities import load_capability_bundles, resolve_bundle_for_tools
from backend.routing.playbooks import Playbook, PlaybookStore
from backend.routing.policies import policy_for_tools
from backend.routing.tool_plan_types import ToolPlan
from backend.tools.catalog import tool_domain

_INTENT_SKILL_MAP: dict[str, str] = {
    "jira.read": "jira_management",
    "jira.read.single": "jira_management",
    "jira.read.list": "jira_management",
    "jira.create": "jira_management",
    "jira.write.assign": "jira_management",
    "jira.write.transition": "jira_management",
    "google.create.sheet": "google_workspace",
    "google.create.doc": "google_workspace",
    "google.read.sheet": "google_workspace",
    "google.read.doc": "google_workspace",
    "slack.summarize.thread": "summarize_bugs",
    "slack.summarize.alerts": "summarize_bugs",
    "repo.docs.qa": "repo_knowledge",
    "slack.board.create": "slack_board_management",
    "slack.board.update": "slack_board_management",
    "slack.board.search": "slack_board_management",
    "script.run": "investigate_bug",
}

_DOMAIN_SKILL_MAP: dict[str, str] = {
    "jira": "jira_management",
    "google_sheet": "google_workspace",
    "google_doc": "google_workspace",
    "slack": "summarize_bugs",
    "slack_write": "slack_board_management",
    "repo_docs": "repo_knowledge",
    "script": "investigate_bug",
    "git": "git_status",
    "git_write": "create_pr",
    "aws": "aws_query",
}


def resolve_policy_skill(
    plan: ToolPlan | None,
    store: PlaybookStore,
    *,
    fallback: Playbook | None,
    data_dir: Path | None = None,
) -> Playbook | None:
    """Pick governance skill from tool plan intent/domain/bundle; fall back to router skill."""
    if plan is None:
        return fallback

    name = _INTENT_SKILL_MAP.get(plan.intent_class or "")
    if not name and plan.intent_class.startswith("template."):
        name = policy_for_tools(plan.tools_needed, data_dir=data_dir)
    if not name and plan.tools_needed:
        bundle_name = resolve_bundle_for_tools(plan.tools_needed, data_dir=data_dir)
        if bundle_name:
            bundle = load_capability_bundles(data_dir).get(bundle_name)
            if bundle and bundle.policy_name:
                name = bundle.policy_name
    if not name and plan.tools_needed:
        domain = tool_domain(plan.tools_needed[0])
        name = _DOMAIN_SKILL_MAP.get(domain, "")

    if name:
        candidate = store.get_by_name(name)
        if candidate is not None:
            return candidate
    return fallback
