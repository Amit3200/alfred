"""Post-loop grounding validation before Alfred replies."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from backend.routing.classifier.intent_classes import is_html_slides_intent
from backend.routing.goal_spec import (
    GoalSpec,
    detect_action_claims,
    extract_artifact_paths,
    extract_urls,
    url_grounding_variants,
    urls_match_for_grounding,
)
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
    "slack_board_create",
    "slack_board_update",
    "slack_board_comment",
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
    for path in extract_artifact_paths(observation):
        urls.add(path)
    try:
        data = json.loads(observation)
    except json.JSONDecodeError:
        return _expand_url_variants(urls)
    if isinstance(data, dict):
        urls.update(extract_urls(json.dumps(data)))
        for key in (
            "url",
            "share_url",
            "slug_url",
            "sha_url",
            "download_url",
            "spreadsheet_url",
            "document_url",
            "html_url",
            "web_url",
            "issue_url",
        ):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                urls.add(value.rstrip(".,)"))
        nested = data.get("data") or data.get("pr") or data.get("issue")
        if isinstance(nested, dict):
            urls.update(_urls_from_observation(json.dumps(nested)))
    return _expand_url_variants(urls)


def _expand_url_variants(urls: set[str]) -> set[str]:
    expanded: set[str] = set()
    for url in urls:
        expanded.update(url_grounding_variants(url))
    return expanded


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


_DOC_PATH_RE = re.compile(r"`([^`]+\.(?:mdx?|markdown|txt|md))`", re.I)
_YES_LEAD_RE = re.compile(r"^\s*\*{0,2}yes\*{0,2}\b", re.I)
_TEMPLATE_URL_RE = re.compile(r"[{}]")


def _doc_read_succeeded(trace: list[ToolTraceEntry]) -> bool:
    return any(entry.tool == "read_repo_doc" and entry.success for entry in trace)


def _template_or_example_urls(urls: set[str]) -> set[str]:
    """Doc handbooks often include placeholder checkout links — not fabrication."""
    return {url for url in urls if _TEMPLATE_URL_RE.search(url)}


_JIRA_BROWSE_RE = re.compile(r"/browse/([A-Z][A-Z0-9]+-\d+)", re.I)


def _url_cites_known_jira_issue(url: str, keys: set[str]) -> bool:
    if not keys:
        return False
    from backend.routing.goal_spec import _canonicalize_url

    match = _JIRA_BROWSE_RE.search(_canonicalize_url(url))
    return bool(match and match.group(1).upper() in keys)


def _url_grounding_issues(
    prose: str,
    trace: list[ToolTraceEntry],
    goal: GoalSpec | None,
) -> list[str]:
    urls_in_text = extract_urls(prose) | extract_artifact_paths(prose)
    if not urls_in_text or not trace:
        return []

    if goal and goal.intent_class == "repo.docs.qa" and _doc_read_succeeded(trace):
        return []

    if goal and str(goal.intent_class or "").startswith("connector."):
        # WhatsApp / connector summaries quote URLs that appeared in chat text.
        # Truncated tool payloads often drop the exact string; do not fail the reply.
        return []

    if goal and is_html_slides_intent(goal.intent_class) and not _artifact_tools_called(trace):
        return []

    urls_from_tools: set[str] = set()
    for entry in trace:
        if entry.success:
            urls_from_tools.update(_urls_from_observation(entry.observation))
    known_keys = _issue_keys_from_trace(trace)

    fabricated_urls = [
        url
        for url in sorted(urls_in_text)
        if url not in _template_or_example_urls(urls_in_text)
        and not any(urls_match_for_grounding(url, tool_url) for tool_url in urls_from_tools)
        and not _url_cites_known_jira_issue(url, known_keys)
    ]
    if not fabricated_urls:
        return []
    return [f"URLs in reply not found in tool results: {', '.join(fabricated_urls[:3])}"]


def _doc_qa_issues(prose: str, trace: list[ToolTraceEntry]) -> list[str]:
    issues: list[str] = []
    doc_tools = frozenset({"search_repo_docs", "read_repo_doc", "list_repo_docs"})
    successful = [entry for entry in trace if entry.success and entry.tool in doc_tools]
    if not successful:
        issues.append("Documentation answer requires search_repo_docs or read_repo_doc in tool trace")
        return issues

    if not any(entry.tool == "search_repo_docs" and entry.success for entry in trace):
        issues.append("Must call search_repo_docs before answering documentation questions")

    search_found_false = False
    observations: list[str] = []
    for entry in trace:
        if not entry.success:
            continue
        observations.append(entry.observation or "")
        if entry.tool == "search_repo_docs" and entry.success:
            obs = (entry.observation or "").lower().replace(" ", "")
            if '"found":false' in obs:
                search_found_false = True
            elif '"found":true' in obs:
                search_found_false = False

    blob = "\n".join(observations)
    if search_found_false and not any(entry.tool == "read_repo_doc" and entry.success for entry in trace):
        if _YES_LEAD_RE.match(prose or ""):
            issues.append("Reply claims support but doc search found no matching documentation")

    for cited in _DOC_PATH_RE.findall(prose or ""):
        if cited not in blob:
            issues.append(f"Cited doc path not present in tool results: {cited}")

    return issues


_ARTIFACT_TOOL_NAMES = frozenset({"save_html_deck", "publish_html_artifact"})


def _artifact_tools_called(trace: list[ToolTraceEntry]) -> bool:
    return any(
        entry.success and entry.tool in _ARTIFACT_TOOL_NAMES for entry in trace
    )


def _html_slides_grounding_issues(
    prose: str,
    trace: list[ToolTraceEntry],
) -> list[str]:
    if _artifact_tools_called(trace):
        return []
    issues: list[str] = []
    cited = extract_urls(prose) | extract_artifact_paths(prose)
    if cited:
        issues.append(
            "HTML slides reply cites a download or share URL but no successful "
            "save_html_deck or publish_html_artifact ran — call the tool first"
        )
        return issues
    if detect_action_claims(prose):
        issues.append(
            "HTML slides require save_html_deck or publish_html_artifact — "
            "reply claimed completion without a successful artifact tool"
        )
    return issues


def _artifact_tool_error(trace: list[ToolTraceEntry]) -> str:
    for entry in reversed(trace):
        if entry.tool not in _ARTIFACT_TOOL_NAMES or entry.success:
            continue
        observation = (entry.observation or "").strip()
        if not observation:
            return f"{entry.tool} failed"
        try:
            data = json.loads(observation)
        except json.JSONDecodeError:
            return observation[:240]
        payload = data.get("data") if isinstance(data.get("data"), dict) else {}
        message = str(payload.get("message") or data.get("message") or "").strip()
        return message or f"{entry.tool} failed"
    return ""


def _html_slides_failure_response(
    trace: list[ToolTraceEntry],
    goal: GoalSpec | None,
    issues: list[str],
) -> str:
    tool_error = _artifact_tool_error(trace)
    if tool_error:
        base = f"I couldn't finish the HTML slide deck: {tool_error}"
    elif goal:
        base = goal.failure_response
    else:
        base = "I couldn't finish the HTML slide deck."

    verified = _format_partial_results(trace)
    parts = [base]
    if verified:
        parts.append(verified)
    parts.append("Issues: " + "; ".join(issues))
    return "\n\n".join(parts)


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

    issues.extend(_url_grounding_issues(prose, trace, goal))

    keys_in_text = {m.group(1).upper() for m in _ISSUE_KEY_RE.finditer(prose)}
    keys_from_tools = _issue_keys_from_trace(trace)
    if keys_in_text and trace and not keys_from_tools.intersection(keys_in_text):
        if goal and goal.intent_class.startswith("jira"):
            issues.append("JIRA issue keys in reply not present in tool trace")

    claims = detect_action_claims(prose)
    successful_tools = {entry.tool for entry in trace if entry.success}
    if claims and not successful_tools and prose:
        if not (goal and is_html_slides_intent(goal.intent_class)):
            issues.append("Action claims in reply but no successful tools were called")

    if goal and is_html_slides_intent(goal.intent_class):
        issues.extend(_html_slides_grounding_issues(prose, trace))

    if goal and goal.intent_class == "repo.docs.qa":
        issues.extend(_doc_qa_issues(prose, trace))

    if issues:
        jira_reply = _successful_jira_action_reply(trace)
        if jira_reply:
            if all(item.startswith("URLs in reply not found") for item in issues):
                return ValidationResult(passed=True)
            return ValidationResult(passed=False, issues=issues, fallback=jira_reply)
        if goal and goal.intent_class.startswith("slack.board."):
            fallback = (
                "I couldn't complete that on the Slack List board. "
                "Try `@alfred create task for …` or `@alfred move ST-1 to in progress`."
            )
            return ValidationResult(passed=False, issues=issues, fallback=fallback)
        if goal and is_html_slides_intent(goal.intent_class):
            fallback = _html_slides_failure_response(trace, goal, issues)
            return ValidationResult(passed=False, issues=issues, fallback=fallback)
        fallback_parts = [goal.failure_response if goal else "I couldn't verify that response against tool results."]
        if goal and goal.intent_class == "repo.docs.qa":
            fallback_parts.append("Issues: " + "; ".join(issues))
        else:
            partial = _format_partial_results(trace)
            if partial:
                fallback_parts.append(partial)
            fallback_parts.append("Issues: " + "; ".join(issues))
        return ValidationResult(passed=False, issues=issues, fallback="\n\n".join(fallback_parts))

    return ValidationResult(passed=True)


def _successful_jira_action_reply(trace: list[ToolTraceEntry]) -> str:
    """User-facing create/update confirmation from a successful JIRA write tool."""
    for entry in reversed(trace):
        if not entry.success:
            continue
        if entry.tool != "jira_create_issue" and entry.result_kind != "jira_action":
            continue
        inner = _observation_data(entry.observation)
        key = str(inner.get("key") or "").strip()
        if not key and entry.tool != "jira_create_issue":
            continue
        from backend.formatting.strategies import format_jira_action

        action = str(inner.get("action") or "create")
        return format_jira_action(action, inner, slack=True)
    return ""


def _observation_payload(observation: str) -> dict[str, Any]:
    try:
        data = json.loads(observation or "")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _observation_data(observation: str) -> dict[str, Any]:
    payload = _observation_payload(observation)
    nested = payload.get("data")
    if isinstance(nested, dict):
        return nested
    return payload


def _script_stdout_json(inner: dict[str, Any]) -> dict[str, Any]:
    parsed = inner.get("json")
    if isinstance(parsed, dict):
        return parsed
    raw = inner.get("stdout")
    if isinstance(raw, str) and raw.strip().startswith("{"):
        try:
            maybe = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(maybe, dict):
            return maybe
    return {}


def _entry_succeeded(entry: ToolTraceEntry) -> bool:
    if not entry.success or entry.result_kind == "error":
        return False
    inner = _observation_data(entry.observation)
    if str(inner.get("status") or "").lower() == "error":
        return False
    if inner.get("ok") is False:
        return False
    exit_code = inner.get("exit_code")
    if exit_code is not None:
        try:
            if int(exit_code) != 0:
                return False
        except (TypeError, ValueError):
            pass
    parsed = _script_stdout_json(inner)
    if parsed and str(parsed.get("status") or "").lower() == "error":
        return False
    return True


def _summarize_tool_entry(entry: ToolTraceEntry) -> str:
    inner = _observation_data(entry.observation)
    kind = entry.result_kind or _observation_payload(entry.observation).get("kind") or ""
    tool = entry.tool

    if kind == "company_script_run" or tool == "run_company_script":
        name = str(inner.get("script") or "script")
        parts = [f"`{name}`"]
        exit_code = inner.get("exit_code")
        if exit_code is not None:
            parts.append(f"exited {exit_code}")
        parsed = _script_stdout_json(inner)
        report_date = str(parsed.get("report_date") or "").strip()
        if report_date:
            parts.append(f"report date {report_date}")
        err = str(
            parsed.get("error") or parsed.get("message") or inner.get("stderr") or ""
        ).strip()
        if err:
            parts.append(err.replace("\n", " ")[:160])
        return " — ".join(parts)

    if kind == "html_artifact_published" or tool == "publish_html_artifact":
        title = str(inner.get("title") or inner.get("slug") or "deck").strip()
        url = str(inner.get("share_url") or inner.get("slug_url") or "").strip()
        if url:
            return f"{title} → `{url}`"
        return title or "published"

    if kind == "html_deck_saved" or tool == "save_html_deck":
        path = str(inner.get("path") or inner.get("filename") or "").strip()
        return f"saved `{path}`" if path else "deck saved"

    message = str(inner.get("message") or "").strip()
    if message:
        return message[:200]
    if kind:
        return str(kind)
    snippet = (entry.observation or "").strip().replace("\n", " ")
    return (snippet[:160] + "…") if len(snippet) > 160 else snippet


def _format_partial_results(trace: list[ToolTraceEntry]) -> str:
    if not trace:
        return ""
    rows: list[str] = []
    failed = 0
    succeeded = 0
    for entry in trace[:8]:
        ok = _entry_succeeded(entry)
        if ok:
            succeeded += 1
            label = "Succeeded"
        else:
            failed += 1
            label = "Failed"
        summary = _summarize_tool_entry(entry)
        rows.append(f"- **{label}** `{entry.tool}` — {summary}")
    if not rows:
        return ""
    counts: list[str] = []
    if failed:
        counts.append(f"{failed} failed")
    if succeeded:
        counts.append(f"{succeeded} succeeded")
    heading = "**Tool results**"
    if counts:
        heading += " — " + ", ".join(counts)
    return heading + "\n\n" + "\n".join(rows)
