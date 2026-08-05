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
