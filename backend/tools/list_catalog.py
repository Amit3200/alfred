"""Build a browsable catalog of all Alfred tools for CLI and Admin UI."""

from __future__ import annotations

from typing import Any

from backend.governance.catalog import (
    WRITE_STAGING_TOOLS,
    is_write_tool,
    requires_confirmation,
)
from backend.models.config import AlfredConfig
from backend.routing.tool_availability import configured_tool_names
from backend.tools.catalog import ALL_KNOWN_TOOLS, tool_category, tool_domain
from backend.tools.catalog_formatter import get_tool_description

_DOMAIN_LABELS: dict[str, str] = {
    "git": "Git & repository",
    "repo_docs": "Repo documentation",
    "jira": "JIRA",
    "identity": "User identity",
    "google_sheet": "Google Sheets",
    "google_doc": "Google Docs",
    "slack": "Slack",
    "aws": "AWS",
    "web": "Web search",
    "script": "Company scripts",
    "schedule": "Schedules",
    "other": "Other",
}


def _integration_requirement(tool_name: str) -> str:
    from backend.tools.catalog import (
        AWS_TOOLS,
        GIT_API_TOOLS,
        GIT_LOCAL_TOOLS,
        GIT_WRITE_TOOLS,
        GOOGLE_TOOLS,
        GRAPHIFY_TOOLS,
        JIRA_TOOLS,
        REPO_DOC_TOOLS,
        SLACK_TOOLS,
        WEB_TOOLS,
    )

    if tool_name in REPO_DOC_TOOLS:
        return "git.enabled + repo_knowledge.enabled"
    if tool_name in GIT_API_TOOLS | GIT_LOCAL_TOOLS | GRAPHIFY_TOOLS:
        return "git.enabled"
    if tool_name in GIT_WRITE_TOOLS:
        return "git.enabled + git.write_enabled"
    if tool_name in JIRA_TOOLS:
        return "jira.enabled"
    if tool_name in {"lookup_user_identity", "build_workspace_identity_map"}:
        return "jira.enabled"
    if tool_name in GOOGLE_TOOLS:
        return "google.enabled"
    if tool_name in AWS_TOOLS:
        return "aws.enabled"
    if tool_name in SLACK_TOOLS:
        return "slack.enabled"
    if tool_name in WEB_TOOLS:
        return "web_search.enabled"
    return "always (scripts.enabled)"


def _governance_level(tool_name: str) -> str:
    if requires_confirmation(tool_name):
        return "confirm"
    if tool_name in WRITE_STAGING_TOOLS:
        return "staging"
    if is_write_tool(tool_name):
        return "write"
    return "read"


def build_tools_catalog(
    config: AlfredConfig,
    *,
    playbooks: list[Any] | None = None,
) -> dict[str, Any]:
    """Structured tool catalog grouped by domain with enablement and governance metadata."""
    enabled_names = configured_tool_names(config)
    skill_index: dict[str, list[str]] = {name: [] for name in ALL_KNOWN_TOOLS}

    for pb in playbooks or []:
        skill_name = getattr(pb, "name", "") or ""
        for tool in getattr(pb, "allowed_tools", []) or []:
            if tool in skill_index and skill_name:
                skill_index[tool].append(skill_name)

    tools: list[dict[str, Any]] = []
    domain_buckets: dict[str, list[dict[str, Any]]] = {}

    for name in sorted(ALL_KNOWN_TOOLS):
        domain = tool_domain(name)
        entry = {
            "name": name,
            "domain": domain,
            "category": tool_category(name),
            "domain_label": _DOMAIN_LABELS.get(domain, domain.replace("_", " ").title()),
            "description": get_tool_description(name),
            "enabled": name in enabled_names,
            "integration": _integration_requirement(name),
            "governance": _governance_level(name),
            "skills": sorted(skill_index.get(name, [])),
        }
        tools.append(entry)
        domain_buckets.setdefault(domain, []).append(entry)

    domains = [
        {
            "name": domain,
            "label": _DOMAIN_LABELS.get(domain, domain.replace("_", " ").title()),
            "tool_count": len(items),
            "enabled_count": sum(1 for t in items if t["enabled"]),
            "tools": items,
        }
        for domain, items in sorted(domain_buckets.items(), key=lambda x: x[0])
    ]

    return {
        "summary": {
            "total": len(tools),
            "enabled": sum(1 for t in tools if t["enabled"]),
            "disabled": sum(1 for t in tools if not t["enabled"]),
            "write_tools": sum(1 for t in tools if t["governance"] != "read"),
            "domain_count": len(domains),
        },
        "domains": domains,
        "tools": tools,
    }


def format_tools_cli(
    catalog: dict[str, Any],
    *,
    enabled_only: bool = False,
    domain: str | None = None,
) -> str:
    """Human-readable table for `alfred tools list`."""
    lines: list[str] = []
    summary = catalog.get("summary") or {}
    lines.append(
        f"Alfred tools: {summary.get('enabled', 0)}/{summary.get('total', 0)} enabled "
        f"({summary.get('write_tools', 0)} write tools)"
    )
    lines.append("")

    for group in catalog.get("domains") or []:
        if domain and group.get("name") != domain:
            continue
        items = [
            t for t in group.get("tools") or []
            if not enabled_only or t.get("enabled")
        ]
        if not items:
            continue
        label = group.get("label") or group.get("name")
        enabled_n = sum(1 for t in items if t.get("enabled"))
        lines.append(f"## {label} ({enabled_n}/{len(items)} enabled)")
        for t in items:
            status = "on" if t.get("enabled") else "off"
            gov = t.get("governance") or "read"
            gov_tag = f" [{gov}]" if gov != "read" else ""
            desc = t.get("description") or ""
            lines.append(f"  • {t['name']:<28} {status:>3}{gov_tag}  {desc}")
            if not t.get("enabled"):
                lines.append(f"      requires: {t.get('integration')}")
            skills = t.get("skills") or []
            if skills:
                lines.append(f"      skills: {', '.join(skills)}")
        lines.append("")

    if domain and not any(
        (g.get("name") == domain and (g.get("tools") or []))
        for g in catalog.get("domains") or []
    ):
        lines.append(f"No tools in domain {domain!r}.")
    return "\n".join(lines).strip() + "\n"
