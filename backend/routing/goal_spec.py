"""GoalSpec — machine-readable success criteria from a tool plan."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.routing.classifier.intent_classes import legacy_intent_class
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
    intent = legacy_intent_class(plan.intent_class) or plan.intent_class

    criteria = [f"Execute tools: {', '.join(plan.tools_needed)}"]
    if intent.startswith("google.create"):
        criteria.append("Reply includes spreadsheet or document URL from tool result")
    if intent.startswith("jira."):
        criteria.append("Reply references JIRA issue key or URL from tool result")
    if intent.startswith("slack.summarize"):
        criteria.append("Summary based on fetched Slack messages, not invented content")
    if intent == "repo.docs.qa":
        criteria.extend(
            [
                "Call search_repo_docs before answering",
                "Use read_repo_doc when the search hit matches the asked integration/feature",
                "Start with Yes or No for support/integration questions",
                "If search finds nothing relevant, answer No — do not cite unrelated docs",
                "Cite doc paths only from tool results",
            ]
        )
    if intent == "slack.board.create":
        criteria.extend(
            [
                "Review scoped board tools in manifest before acting",
                "Use slack_fetch_thread when thread context is needed",
                "Call slack_board_create_task for the mutation unless bootstrap already succeeded",
                "Include display id, record id, title, and status when present",
                "Do not invent task ids",
            ]
        )
    if intent == "slack.board.update":
        criteria.extend(
            [
                "Review scoped board tools in manifest before acting",
                "Use slack_board_search_tasks or slack_board_get_task when task id is unclear",
                "Call slack_board_update_task for status/assignee/severity changes",
                "Do not invent task ids",
            ]
        )
    if intent == "slack.board.comment":
        criteria.extend(
            [
                "Use read tools to resolve task id when needed",
                "Call slack_board_comment for the mutation",
            ]
        )
    if intent.startswith("slack.board."):
        requires_write = requires_write or intent in (
            "slack.board.create",
            "slack.board.update",
            "slack.board.comment",
        )

    if intent == "html_slides":
        criteria.extend(
            [
                "Call save_html_deck (or publish_html_artifact when user asked to publish)",
                "Do not claim the deck was saved without a successful artifact tool",
                "Reply includes download path or share URL from tool result",
            ]
        )

    failure = plan.goal
    if intent == "repo.docs.qa":
        failure = (
            "I couldn't answer from indexed documentation. "
            "Try rephrasing or check Knowledge bases → FlexyPe/docs is indexed."
        )
    if intent.startswith("slack.board."):
        failure = (
            "I couldn't complete that on the Slack List board. "
            "Try `@alfred create task for …` or `@alfred move ST-1 to in progress`."
        )
    if intent == "html_slides":
        publish_tools = [t for t in plan.tools_needed if t == "publish_html_artifact"]
        if publish_tools:
            failure = (
                "I couldn't finish the HTML slide deck. "
                "I'll build the deck, call save_html_deck, then publish_html_artifact "
                "and report the share URL from the tool result."
            )
        else:
            failure = (
                "I couldn't save the HTML slide deck. "
                "Try again — I'll call save_html_deck with the full HTML file."
            )
    if plan.missing_capabilities:
        failure = (
            f"I can't complete this yet — missing tools: {', '.join(plan.missing_capabilities)}."
        )

    return GoalSpec(
        intent_class=intent or "unknown",
        goal=plan.goal,
        required_tools=list(plan.tools_needed),
        success_criteria=criteria,
        failure_response=failure,
        requires_write=requires_write,
    )


def extract_urls(text: str) -> set[str]:
    return {match.group(0).rstrip(".,)") for match in _URL_RE.finditer(text or "")}


_ARTIFACT_PATH_RE = re.compile(
    r"(/(?:artifacts/(?:s|sha)/[^\s<>\"']+|api/chat/exports/[^\s<>\"']+))",
    re.I,
)


def extract_artifact_paths(text: str) -> set[str]:
    """Relative artifact/export paths cited in prose (not caught by http URL regex)."""
    return {match.group(1).rstrip(".,)") for match in _ARTIFACT_PATH_RE.finditer(text or "")}


def url_grounding_variants(url: str) -> set[str]:
    """Equivalent URL forms for grounding (absolute vs path-only)."""
    cleaned = (url or "").strip().rstrip(".,)")
    if not cleaned:
        return set()
    variants = {cleaned}
    if cleaned.startswith(("http://", "https://")):
        from urllib.parse import urlparse

        parsed = urlparse(cleaned)
        if parsed.path:
            variants.add(parsed.path)
            if parsed.netloc:
                variants.add(f"{parsed.scheme}://{parsed.netloc}{parsed.path}")
    elif cleaned.startswith("/"):
        variants.add(cleaned)
    return variants


def urls_match_for_grounding(left: str, right: str) -> bool:
    return bool(url_grounding_variants(left) & url_grounding_variants(right))


def detect_action_claims(text: str) -> list[str]:
    return list({m.group(1).lower() for m in _WRITE_VERBS.finditer(text or "")})
