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
    "jira.write.create": "jira_management",
    "jira.write.comment": "jira_management",
    "jira.write.update": "jira_management",
    "jira.write.link": "jira_management",
    "html_slides": "html_slides",
    "artifact.write.deck": "html_slides",
    "slack.board.create": "slack_board_management",
    "slack.board.update": "slack_board_management",
    "slack.board.search": "slack_board_management",
    "slack.board.config": "slack_board_management",
    "slack.board.write.create": "slack_board_management",
    "slack.board.write.update": "slack_board_management",
    "slack.board.write.comment": "slack_board_management",
    "slack.board.read.search": "slack_board_management",
    "connector.read": "connector_management",
    "connector.read.list": "connector_management",
    "connector.read.chats": "connector_management",
    "connector.read.tickets": "connector_management",
    "connector.read.tasks": "connector_management",
    "connector.read.messages": "connector_management",
    "connector.read.poll": "connector_management",
}

_DOMAIN_SKILL_MAP: dict[str, str] = {
    "jira": "jira_management",
    "google_sheet": "google_workspace",
    "google_doc": "google_workspace",
    "slack": "summarize_bugs",
    "slack_write": "slack_board_management",
    "repo_docs": "repo_knowledge",
    "artifact": "html_slides",
    "git": "git_status",
    "git_write": "create_pr",
    "aws": "aws_query",
    "connector": "connector_management",
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

    if fallback is not None and plan.tools_needed:
        allowed = set(fallback.allowed_tools or [])
        needed = {tool for tool in plan.tools_needed if tool}
        if allowed and needed and needed <= allowed:
            return fallback

    name = _INTENT_SKILL_MAP.get(plan.intent_class or "")
    if plan.intent_class.startswith("template."):
        template_name = plan.intent_class.split(".", 1)[1].strip()
        if template_name:
            templated = store.get_by_name(template_name)
            if templated is not None:
                return templated
        if not name:
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

    if not name and (plan.intent_class or "").startswith("connector."):
        name = "connector_management"

    if name:
        candidate = store.get_by_name(name)
        if candidate is not None:
            return candidate
    return fallback
