"""Capability bundles — tool groups, context injectors, and policy mappings."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from backend.tools.catalog import (
    AWS_TOOLS,
    COMPANY_SCRIPT_TOOLS,
    GIT_API_TOOLS,
    GIT_LOCAL_TOOLS,
    GOOGLE_DOC_TOOLS,
    GOOGLE_SHEET_TOOLS,
    GRAPHIFY_TOOLS,
    IDENTITY_TOOLS,
    JIRA_TOOLS,
    REPO_DOC_TOOLS,
    CONNECTOR_TOOLS,
    SCHEDULE_TOOLS,
    SLACK_TOOLS,
    WEB_TOOLS,
)

DEFAULT_BUNDLE_POLICY: dict[str, str] = {
    "jira": "jira_management",
    "google": "google_workspace",
    "google_sheet": "google_workspace",
    "google_doc": "google_workspace",
    "slack_read": "summarize_bugs",
    "repo": "investigate_bug",
    "repo_docs": "repo_knowledge",
    "script": "investigate_bug",
    "aws": "aws_query",
    "schedule": "schedule_management",
    "web": "web_research",
    "git": "git_status",
    "connector": "connector_management",
}


@dataclass(frozen=True)
class CapabilityBundle:
    name: str
    tools: frozenset[str]
    policy_name: str = ""
    context_injectors: tuple[str, ...] = ()
    subagent: str = ""
    output_format: str = ""


def _default_bundles() -> dict[str, CapabilityBundle]:
    repo_tools = GIT_API_TOOLS | GIT_LOCAL_TOOLS | GRAPHIFY_TOOLS | REPO_DOC_TOOLS
    return {
        "jira": CapabilityBundle(
            name="jira",
            tools=JIRA_TOOLS | IDENTITY_TOOLS,
            policy_name="jira_management",
            context_injectors=("jira_context",),
            subagent="jira_worker",
            output_format="jira_summary",
        ),
        "google_sheet": CapabilityBundle(
            name="google_sheet",
            tools=GOOGLE_SHEET_TOOLS,
            policy_name="google_workspace",
            context_injectors=("google_context",),
            subagent="google_worker",
            output_format="google_sheet",
        ),
        "google_doc": CapabilityBundle(
            name="google_doc",
            tools=GOOGLE_DOC_TOOLS,
            policy_name="google_workspace",
            context_injectors=("google_context",),
            subagent="google_worker",
            output_format="google_doc",
        ),
        "google": CapabilityBundle(
            name="google",
            tools=GOOGLE_SHEET_TOOLS | GOOGLE_DOC_TOOLS,
            policy_name="google_workspace",
            context_injectors=("google_context",),
            subagent="google_worker",
        ),
        "slack_read": CapabilityBundle(
            name="slack_read",
            tools=SLACK_TOOLS,
            policy_name="summarize_bugs",
            context_injectors=("slack_context",),
            subagent="slack_worker",
            output_format="slack_summary",
        ),
        "repo": CapabilityBundle(
            name="repo",
            tools=repo_tools,
            policy_name="investigate_bug",
            context_injectors=("git_context", "repo_context"),
            subagent="repo_worker",
        ),
        "repo_docs": CapabilityBundle(
            name="repo_docs",
            tools=REPO_DOC_TOOLS,
            policy_name="repo_knowledge",
            context_injectors=("repo_context",),
            output_format="doc_search",
        ),
        "script": CapabilityBundle(
            name="script",
            tools=COMPANY_SCRIPT_TOOLS,
            policy_name="investigate_bug",
            subagent="script_worker",
        ),
        "aws": CapabilityBundle(
            name="aws",
            tools=AWS_TOOLS,
            policy_name="aws_query",
            output_format="athena_query",
        ),
        "schedule": CapabilityBundle(
            name="schedule",
            tools=SCHEDULE_TOOLS,
            policy_name="schedule_management",
        ),
        "connector": CapabilityBundle(
            name="connector",
            tools=CONNECTOR_TOOLS,
            policy_name="connector_management",
        ),
        "web": CapabilityBundle(
            name="web",
            tools=WEB_TOOLS,
            policy_name="web_research",
        ),
        "git": CapabilityBundle(
            name="git",
            tools=GIT_API_TOOLS,
            policy_name="git_status",
        ),
        "jira.write.create": CapabilityBundle(
            name="jira.write.create",
            tools=frozenset({"jira_create_issue"}),
            policy_name="jira_management",
            context_injectors=("jira_context",),
            output_format="jira_summary",
        ),
        "jira.write.assign": CapabilityBundle(
            name="jira.write.assign",
            tools=frozenset({"jira_assign_issue"}),
            policy_name="jira_management",
            context_injectors=("jira_context",),
        ),
        "jira.write.transition": CapabilityBundle(
            name="jira.write.transition",
            tools=frozenset({"transition_jira_issue"}),
            policy_name="jira_management",
            context_injectors=("jira_context",),
        ),
        "jira.write.comment": CapabilityBundle(
            name="jira.write.comment",
            tools=frozenset({"jira_add_comment"}),
            policy_name="jira_management",
            context_injectors=("jira_context",),
        ),
        "jira.write.update": CapabilityBundle(
            name="jira.write.update",
            tools=frozenset({"jira_update_issue"}),
            policy_name="jira_management",
            context_injectors=("jira_context",),
        ),
        "jira.write.link": CapabilityBundle(
            name="jira.write.link",
            tools=frozenset({"link_jira_issue"}),
            policy_name="jira_management",
            context_injectors=("jira_context",),
        ),
        "jira.read.single": CapabilityBundle(
            name="jira.read.single",
            tools=frozenset({"get_jira_issue"}),
            policy_name="jira_management",
            context_injectors=("jira_context",),
            output_format="jira_summary",
        ),
        "jira.read.list": CapabilityBundle(
            name="jira.read.list",
            tools=frozenset({"jira_search", "list_jira_issues"}),
            policy_name="jira_management",
            context_injectors=("jira_context",),
            output_format="jira_summary",
        ),
        "slack.board.write.create": CapabilityBundle(
            name="slack.board.write.create",
            tools=frozenset({"slack_fetch_thread", "slack_board_create_task"}),
            policy_name="slack_board_management",
            context_injectors=("slack_context",),
        ),
        "slack.board.write.update": CapabilityBundle(
            name="slack.board.write.update",
            tools=frozenset({"slack_board_update_task"}),
            policy_name="slack_board_management",
            context_injectors=("slack_context",),
        ),
        "slack.board.write.comment": CapabilityBundle(
            name="slack.board.write.comment",
            tools=frozenset({"slack_board_comment"}),
            policy_name="slack_board_management",
            context_injectors=("slack_context",),
        ),
        "slack.board.read.search": CapabilityBundle(
            name="slack.board.read.search",
            tools=frozenset({"slack_board_search_tasks", "slack_board_get_task"}),
            policy_name="slack_board_management",
            context_injectors=("slack_context",),
        ),
        "artifact.write.deck": CapabilityBundle(
            name="artifact.write.deck",
            tools=frozenset({"save_html_deck", "publish_html_artifact"}),
            policy_name="html_slides",
        ),
        "repo.docs.qa": CapabilityBundle(
            name="repo.docs.qa",
            tools=frozenset({"search_repo_docs", "read_repo_doc"}),
            policy_name="repo_knowledge",
            context_injectors=("repo_context",),
            output_format="doc_search",
        ),
        "identity.lookup": CapabilityBundle(
            name="identity.lookup",
            tools=frozenset({"lookup_user_identity"}),
            policy_name="jira_management",
        ),
        "git.pr.review": CapabilityBundle(
            name="git.pr.review",
            tools=frozenset({"get_pr", "get_pr_changes"}),
            policy_name="review_pr",
        ),
        "git.pr.read": CapabilityBundle(
            name="git.pr.read",
            tools=frozenset({"list_my_prs", "list_prs", "get_pr", "get_pr_changes"}),
            policy_name="git_status",
        ),
        "google.write.sheet": CapabilityBundle(
            name="google.write.sheet",
            tools=frozenset({"google_create_sheet", "google_write_sheet", "google_append_sheet"}),
            policy_name="google_workspace",
        ),
        "google.read.sheet": CapabilityBundle(
            name="google.read.sheet",
            tools=frozenset({"google_read_sheet"}),
            policy_name="google_workspace",
        ),
        "git.repo.read": CapabilityBundle(
            name="git.repo.read",
            tools=frozenset({"grep_repo", "read_file", "query_graph"}),
            policy_name="investigate_bug",
        ),
        "aws.read.query": CapabilityBundle(
            name="aws.read.query",
            tools=AWS_TOOLS,
            policy_name="aws_query",
        ),
        "web.search": CapabilityBundle(
            name="web.search",
            tools=WEB_TOOLS,
            policy_name="web_research",
        ),
        "slack.read.thread": CapabilityBundle(
            name="slack.read.thread",
            tools=SLACK_TOOLS,
            policy_name="summarize_bugs",
        ),
        "google.write.doc": CapabilityBundle(
            name="google.write.doc",
            tools=frozenset({"google_create_doc", "google_append_doc"}),
            policy_name="google_workspace",
        ),
        "google.read.doc": CapabilityBundle(
            name="google.read.doc",
            tools=frozenset({"google_read_doc"}),
            policy_name="google_workspace",
        ),
        "script.run": CapabilityBundle(
            name="script.run",
            tools=COMPANY_SCRIPT_TOOLS,
            policy_name="investigate_bug",
        ),
        "schedule.write.create": CapabilityBundle(
            name="schedule.write.create",
            tools=frozenset({"create_schedule"}),
            policy_name="schedule_management",
        ),
        "schedule.read.list": CapabilityBundle(
            name="schedule.read.list",
            tools=frozenset({"list_schedules"}),
            policy_name="schedule_management",
        ),
        "schedule.write.toggle": CapabilityBundle(
            name="schedule.write.toggle",
            tools=frozenset({"toggle_schedule"}),
            policy_name="schedule_management",
        ),
        "schedule.write.delete": CapabilityBundle(
            name="schedule.write.delete",
            tools=frozenset({"delete_schedule"}),
            policy_name="schedule_management",
        ),
        "schedule.write.update": CapabilityBundle(
            name="schedule.write.update",
            tools=frozenset({"update_schedule"}),
            policy_name="schedule_management",
        ),
    }


def load_capability_bundles(data_dir: Path | None = None) -> dict[str, CapabilityBundle]:
    """Load bundles from `.alfred/capabilities.yaml` or built-in defaults."""
    bundles = _default_bundles()
    if data_dir is None:
        return bundles

    path = data_dir / "capabilities.yaml"
    if not path.is_file():
        return bundles

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return bundles

    items = raw.get("bundles") if isinstance(raw, dict) else None
    if not isinstance(items, dict):
        return bundles

    merged = dict(bundles)
    for name, spec in items.items():
        if not isinstance(spec, dict):
            continue
        tools_raw = spec.get("tools") or []
        if not isinstance(tools_raw, list):
            continue
        base = merged.get(name)
        merged[name] = CapabilityBundle(
            name=name,
            tools=frozenset(str(t) for t in tools_raw),
            policy_name=str(spec.get("policy_name") or (base.policy_name if base else DEFAULT_BUNDLE_POLICY.get(name, ""))),
            context_injectors=tuple(spec.get("context_injectors") or (base.context_injectors if base else ())),
            subagent=str(spec.get("subagent") or (base.subagent if base else "")),
            output_format=str(spec.get("output_format") or (base.output_format if base else "")),
        )
    return merged


def bundle_tools(bundle_name: str, *, data_dir: Path | None = None) -> list[str]:
    bundle = load_capability_bundles(data_dir).get(bundle_name)
    return sorted(bundle.tools) if bundle else []


def tools_for_capability(capability: str, *, data_dir: Path | None = None) -> list[str]:
    """Tools for a capability key, falling back to the intent→tool table."""
    from backend.routing.classifier.intent_classes import INTENT_TO_TOOLS, canonical_intent_class

    name = (capability or "").strip()
    tools = bundle_tools(name, data_dir=data_dir)
    if tools:
        return tools
    canonical = canonical_intent_class(name)
    return list(INTENT_TO_TOOLS.get(canonical, ()))


def capability_for_tool(
    tool_name: str,
    *,
    candidates: tuple[str, ...] | None = None,
    data_dir: Path | None = None,
) -> str:
    """Fine-grained capability that owns this tool (prefer dotted keys)."""
    name = (tool_name or "").strip()
    if not name:
        return ""
    bundles = load_capability_bundles(data_dir)
    keys = list(candidates) if candidates else list(bundles)
    best = ""
    best_score = -1
    for key in keys:
        bundle = bundles.get(key)
        if bundle is None or name not in bundle.tools:
            continue
        score = key.count(".")
        if score > best_score:
            best = key
            best_score = score
    if best:
        return best
    from backend.routing.classifier.intent_classes import INTENT_TO_TOOLS

    for intent, tools in INTENT_TO_TOOLS.items():
        if name in tools and (candidates is None or intent in candidates):
            return intent
    return ""


def resolve_bundle_for_tools(tool_names: list[str], *, data_dir: Path | None = None) -> str:
    """Best-matching bundle name for a tool list."""
    names = set(tool_names)
    if not names:
        return ""
    bundles = load_capability_bundles(data_dir)
    best_name = ""
    best_overlap = 0
    for name, bundle in bundles.items():
        overlap = len(names & bundle.tools)
        if overlap > best_overlap:
            best_overlap = overlap
            best_name = name
    return best_name if best_overlap else ""
