"""Direct Git tool routing — bypass LLM for common, unambiguous questions."""

from __future__ import annotations

import json
import re
from typing import Any

from backend.ingress.playbooks import Playbook
from backend.models.config import GitConfig

_MY_PRS_RE = re.compile(
    r"\b("
    r"my\s+(?:open\s+)?(?:pull\s+requests?|prs?)"
    r"|(?:open\s+)?prs?\s+of\s+mine"
    r"|(?:pull\s+requests?|prs?)\s+(?:i\s+)?(?:have\s+)?open"
    r"|what\s+are\s+(?:my\s+)?(?:open\s+)?prs?"
    r"|list\s+my\s+(?:open\s+)?prs?"
    r"|any\s+open\s+prs?\s+(?:of\s+)?mine"
    r")\b",
    re.I,
)

_REPO_PRS_RE = re.compile(
    r"\b(?:open\s+)?prs?\s+(?:on|in|for)\s+([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)\b",
    re.I,
)

_PR_NUMBER_RE = re.compile(
    r"(?:#|(?:pr|pull\s+request|merge\s+request)\s*#)(\d+)\b",
    re.I,
)

_LIST_REPOS_RE = re.compile(
    r"\b(?:list|show)\s+(?:me\s+)?(?:the\s+)?(?:repos|repositories)\b",
    re.I,
)

_GITHUB_PR_URL_RE = re.compile(
    r"github\.com/([^/\s>|]+)/([^/\s>|]+)/pull/(\d+)",
    re.I,
)

_GITLAB_MR_URL_RE = re.compile(
    r"gitlab\.com/(.+?)/-/merge_requests/(\d+)",
    re.I,
)

_SUMMARY_HINTS = (
    "summar",
    "what does",
    "what do ",
    "describe",
    "explain",
    "tell me what",
    "tell me about",
)

_CODE_ANALYSIS_HINTS = (
    "review",
    "code review",
    "what does",
    "what do ",
    "navigate",
    "explore",
    "understand",
    "walk through",
    "walk me through",
    "look at the code",
    "see what",
    "how does",
    "explain this pr",
    "explain the pr",
    "what changed",
    "what it does",
    "what this pr",
    "investigate this pr",
    "analyze",
    "analyse",
)

_PR_FOLLOWUP_HINTS = (
    "business impact",
    "what does",
    "what do ",
    "what is it",
    "what's it",
    "what is this",
    "explain",
    "tell me more",
    "how does it work",
    "what it does",
    "what is this pr",
    "what's this pr",
    "all about",
    "why",
    "purpose",
)

_TEXT_TOOL_CALL_RE = re.compile(
    r'\{\s*"name"\s*:\s*"([a-z_]+)"\s*,\s*"parameters"\s*:?\s*(\{.*?\})\s*\}',
    re.I | re.DOTALL,
)


def extract_pr_reference(text: str) -> tuple[str, int] | None:
    """Parse owner/repo and PR number from GitHub/GitLab URLs (including Slack links)."""
    if match := _GITHUB_PR_URL_RE.search(text):
        return f"{match.group(1)}/{match.group(2)}", int(match.group(3))
    if match := _GITLAB_MR_URL_RE.search(text):
        return match.group(1), int(match.group(2))
    return None


def wants_pr_summary(intent: str) -> bool:
    lower = intent.lower()
    return any(hint in lower for hint in _SUMMARY_HINTS)


def wants_pr_code_analysis(intent: str) -> bool:
    """True when the user wants a code-level PR review or exploration."""
    lower = intent.lower()
    if not extract_pr_reference(intent):
        return False
    if any(hint in lower for hint in _CODE_ANALYSIS_HINTS):
        return True
    # "summarize and review" — review wins over metadata-only summary
    return "review" in lower and wants_pr_summary(lower)


def wants_pr_followup(intent: str) -> bool:
    """Follow-up questions in a thread that already discussed a PR."""
    lower = intent.lower()
    return any(hint in lower for hint in _PR_FOLLOWUP_HINTS)


def extract_pr_from_session(session: Any) -> tuple[str, int] | None:
    """Recover PR repo/number from session metadata or prior turns."""
    active = (session.metadata or {}).get("active_pr") if session else None
    if isinstance(active, dict) and active.get("repo") and active.get("number"):
        return str(active["repo"]), int(active["number"])

    if not session:
        return None
    for turn in reversed(session.turns):
        if ref := extract_pr_reference(turn.content):
            return ref
    return None


def resolve_pr_for_analysis(intent: str, session: Any | None) -> tuple[str, int] | None:
    """PR reference from the current message or conversation session."""
    if ref := extract_pr_reference(intent):
        return ref
    if session:
        return extract_pr_from_session(session)
    return None


def should_run_pr_analysis(intent: str, session: Any | None) -> bool:
    """Whether to run the direct PR fetch + diff analysis path."""
    if extract_pr_reference(intent):
        return wants_pr_code_analysis(intent)
    if session and extract_pr_from_session(session):
        return wants_pr_followup(intent)
    return False


def pr_analysis_focus(intent: str) -> str:
    """Prompt focus: technical review vs business impact."""
    lower = intent.lower()
    if any(h in lower for h in ("business impact", "business", "all about", "why", "purpose")):
        return "business"
    return "review"


def detect_git_direct_action(
    intent: str,
    skill: Playbook,
    git: GitConfig | None = None,
) -> tuple[str, dict[str, Any]] | None:
    """Return (tool_name, args) when the question maps cleanly to one Git API tool."""
    if skill.name != "git_status":
        return None

    lower = intent.lower().strip()
    state = _pr_state_from_intent(lower)

    if _MY_PRS_RE.search(lower):
        return "list_my_prs", {"state": state}

    if ref := extract_pr_reference(intent):
        return "get_pr", {"repo": ref[0], "number": ref[1]}

    if match := _REPO_PRS_RE.search(intent):
        return "list_prs", {"repo": match.group(1), "state": state}

    if _LIST_REPOS_RE.search(lower):
        return "list_repos", {}

    if match := _PR_NUMBER_RE.search(intent):
        repo = _extract_repo_slug(intent, git)
        if repo:
            return "get_pr", {"repo": repo, "number": int(match.group(1))}

    return None


def normalize_tool_arguments(
    tool_name: str,
    arguments: dict[str, Any],
    git: GitConfig,
) -> dict[str, Any]:
    """Fix common model mistakes (short repo names) before calling Git API."""
    from backend.git.api import resolve_repo_slug

    args = dict(arguments)
    repo_tools = ("get_pr", "get_pr_changes", "list_prs", "grep_repo", "read_file", "git_log", "git_blame", "git_show")
    if tool_name in repo_tools and args.get("repo"):
        repo = str(args["repo"]).strip()
        try:
            args["repo"] = resolve_repo_slug(repo, git)
        except ValueError:
            if ref := extract_pr_reference(repo):
                args["repo"] = ref[0]
                if tool_name == "get_pr" and not args.get("number"):
                    args["number"] = ref[1]
    return args


def parse_text_tool_call(content: str) -> tuple[str, dict[str, Any]] | None:
    """Parse tool calls some models emit as JSON text instead of structured tool_calls."""
    text = content.strip()
    if not text.startswith("{") or "name" not in text:
        return None

    for candidate in (text, _fix_malformed_tool_json(text)):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        name = data.get("name") or data.get("tool")
        if not isinstance(name, str):
            continue
        params = data.get("parameters") or data.get("arguments") or data.get("input") or {}
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                params = {}
        if not isinstance(params, dict):
            params = {}
        return name, params

    match = _TEXT_TOOL_CALL_RE.search(text)
    if match:
        name = match.group(1)
        try:
            params = json.loads(_fix_malformed_tool_json(match.group(2)))
        except json.JSONDecodeError:
            params = {}
        if not isinstance(params, dict):
            params = {}
        return name, params

    return None


def looks_like_tool_json(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("{") and '"name"' in stripped and (
        "parameters" in stripped or "arguments" in stripped
    )


def _pr_state_from_intent(lower: str) -> str:
    if "closed" in lower or "merged" in lower:
        return "closed"
    if "all" in lower:
        return "all"
    return "open"


def _extract_repo_slug(intent: str, git: GitConfig | None) -> str | None:
    if ref := extract_pr_reference(intent):
        return ref[0]
    if match := _REPO_PRS_RE.search(intent):
        return match.group(1)
    match = re.search(r"\b([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)\b", intent)
    if match:
        return match.group(1)
    if git and git.default_org:
        repo_match = re.search(
            r"\b(?:repo(?:sitory)?|on|in)\s+([a-zA-Z0-9_.-]+)\b",
            intent,
            re.I,
        )
        if repo_match:
            from backend.git.api import resolve_repo_slug

            try:
                return resolve_repo_slug(repo_match.group(1), git)
            except ValueError:
                return None
    return None


def _fix_malformed_tool_json(text: str) -> str:
    """Best-effort repair for models that omit colons/quotes in tool JSON."""
    fixed = text.strip()
    fixed = re.sub(r'"parameters"\s*\{', '"parameters": {', fixed)
    fixed = re.sub(r'"parameters\s*\{', '"parameters": {', fixed)
    fixed = re.sub(r'"(\w+)""\s*:', r'"\1":', fixed)
    fixed = re.sub(r':\s*""([^"]+)""', r': "\1"', fixed)
    if fixed.count("{") > fixed.count("}"):
        fixed += "}" * (fixed.count("{") - fixed.count("}"))
    return fixed
