"""Post-loop grounding validation before Alfred replies."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from backend.routing.goal_spec import GoalSpec, detect_action_claims, extract_urls
from backend.tools.catalog import GIT_WRITE_TOOLS, JIRA_TOOLS

_ISSUE_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")

_WRITE_TOOL_PREFIXES = (
    "jira_create",
    "jira_update",
    "jira_assign",
    "transition_jira",
    "link_jira",
    "add_jira",
    "jira_add",
    "google_create",
    "google_write",
    "google_append",
    "git_push",
    "create_pull",
    "write_file",
    "git_commit",
)


@dataclass
class ToolTraceEntry:
    tool: str
    success: bool
    result_kind: str = ""
    observation: str = ""


@dataclass
class ValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)
    fallback: str = ""


def _urls_from_observation(observation: str) -> set[str]:
    urls = set(extract_urls(observation))
    try:
        data = json.loads(observation)
    except json.JSONDecodeError:
        return urls
    if isinstance(data, dict):
        urls.update(extract_urls(json.dumps(data)))
        for key in ("url", "spreadsheet_url", "document_url", "html_url", "web_url"):
            value = data.get(key)
            if isinstance(value, str) and value.startswith("http"):
                urls.add(value.rstrip(".,)"))
        nested = data.get("data") or data.get("pr") or data.get("issue")
        if isinstance(nested, dict):
            urls.update(_urls_from_observation(json.dumps(nested)))
    return urls


def _issue_keys_from_trace(trace: list[ToolTraceEntry]) -> set[str]:
    keys: set[str] = set()
    for entry in trace:
        for match in _ISSUE_KEY_RE.finditer(entry.observation):
            keys.add(match.group(1).upper())
    return keys


def _write_tools_called(trace: list[ToolTraceEntry]) -> list[str]:
    out: list[str] = []
    for entry in trace:
        if not entry.success:
            continue
        name = entry.tool
        if name in JIRA_TOOLS or name in GIT_WRITE_TOOLS:
            if any(name.startswith(prefix) or prefix in name for prefix in _WRITE_TOOL_PREFIXES):
                out.append(name)
            elif name.startswith("google_") and "read" not in name and "get" not in name:
                out.append(name)
    return out


def validate_agent_result(
    text: str,
    trace: list[ToolTraceEntry],
    goal: GoalSpec | None = None,
) -> ValidationResult:
    issues: list[str] = []
    prose = (text or "").strip()

    if goal and goal.requires_write:
        writes = _write_tools_called(trace)
        if not writes:
            issues.append("Write goal but no successful write tool in trace")

    urls_in_text = extract_urls(prose)
    urls_from_tools: set[str] = set()
    for entry in trace:
        if entry.success:
            urls_from_tools.update(_urls_from_observation(entry.observation))

    fabricated_urls = urls_in_text - urls_from_tools
    if fabricated_urls and trace:
        issues.append(f"URLs in reply not found in tool results: {', '.join(sorted(fabricated_urls)[:3])}")

    keys_in_text = {m.group(1).upper() for m in _ISSUE_KEY_RE.finditer(prose)}
    keys_from_tools = _issue_keys_from_trace(trace)
    if keys_in_text and trace and not keys_from_tools.intersection(keys_in_text):
        if goal and goal.intent_class.startswith("jira"):
            issues.append("JIRA issue keys in reply not present in tool trace")

    claims = detect_action_claims(prose)
    successful_tools = {entry.tool for entry in trace if entry.success}
    if claims and not successful_tools and prose:
        issues.append("Action claims in reply but no successful tools were called")

    if issues:
        partial = _format_partial_results(trace)
        fallback_parts = [goal.failure_response if goal else "I couldn't verify that response against tool results."]
        if partial:
            fallback_parts.append(partial)
        fallback_parts.append("Issues: " + "; ".join(issues))
        return ValidationResult(passed=False, issues=issues, fallback="\n\n".join(fallback_parts))

    return ValidationResult(passed=True)


def _format_partial_results(trace: list[ToolTraceEntry]) -> str:
    lines: list[str] = []
    for entry in trace:
        if not entry.success:
            continue
        snippet = entry.observation.strip()
        if len(snippet) > 400:
            snippet = snippet[:400] + "…"
        lines.append(f"- `{entry.tool}` ({entry.result_kind or 'ok'}): {snippet}")
    if not lines:
        return ""
    return "**Verified tool results:**\n" + "\n".join(lines[:5])
