"""Session git context — thread hints, follow-ups, and tool arg enrichment."""

from __future__ import annotations

import re
from typing import Any

from backend.integrations.git.api import resolve_repo_slug
from backend.routing.git.direct import extract_pr_reference
from backend.models.config import GitConfig

_RETRY_RE = re.compile(
    r"\b("
    r"retry"
    r"|try again"
    r"|run again"
    r"|same (?:pr|repo|question)"
    r"|that again"
    r"|above"
    r"|as above"
    r"|like before"
    r")\b",
    re.I,
)

_SAME_PR_RE = re.compile(
    r"\b(same pr|that pr|this pr|the pr|that pull request)\b",
    re.I,
)

_WHERE_HANDLED_RE = re.compile(
    r"\b(?:where is|where does|where are|how is|how does)\s+(.+?)\s+"
    r"(?:handled|defined|implemented|used|called)?\s*(?:in|on|for)\s+"
    r"([a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)?)\b",
    re.I,
)

_FIND_IN_RE = re.compile(
    r"\b(?:find|search for|grep|look for)\s+(.+?)\s+in\s+"
    r"([a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)?)\b",
    re.I,
)

_FILE_LINE_RE = re.compile(
    r"[`']?([\w./-]+\.(?:py|js|ts|tsx|go|rb|java|kt|rs|yaml|yml|md|json)):(\d+)[`']?",
    re.I,
)

_REPO_IN_TEXT_RE = re.compile(r"\b([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)\b")

_WHAT_USE_FOR_RE = re.compile(
    r"\bwhat\s+(?:do\s+we|are\s+we)\s+(?:use|using)\s+for\s+(.+?)(?:\?|\s+do\s+we\b|\s*$)",
    re.I,
)

_LOCAL_REPO_TOOLS = frozenset(
    {"grep_repo", "read_file", "git_log", "git_blame", "git_show"}
)
_API_REPO_TOOLS = frozenset({"get_pr", "get_pr_changes", "list_prs"})


def wants_git_retry(intent: str) -> bool:
    return bool(_RETRY_RE.search(intent.lower()))


def wants_same_pr(intent: str) -> bool:
    return bool(_SAME_PR_RE.search(intent.lower()))


def extract_file_line_hint(text: str) -> tuple[str, int] | None:
    if match := _FILE_LINE_RE.search(text):
        return match.group(1), int(match.group(2))
    return None


def session_history_texts(session: Any | None, intent: str = "", *, limit: int = 6) -> list[str]:
    """Recent thread messages plus the current intent."""
    texts = [intent] if intent else []
    if session:
        texts.extend(turn.content for turn in session.turns[-limit:])
    return texts


def collect_thread_git_hints(*texts: str) -> dict[str, Any]:
    """Gather repo, file:line, and PR references from message + history."""
    hints: dict[str, Any] = {
        "repos": [],
        "file_lines": [],
        "pr_refs": [],
        "search_terms": [],
    }
    seen_repos: set[str] = set()
    seen_files: set[str] = set()

    for text in texts:
        if not text:
            continue
        if ref := extract_pr_reference(text):
            hints["pr_refs"].append({"repo": ref[0], "number": ref[1]})
        for match in _REPO_IN_TEXT_RE.finditer(text):
            repo = match.group(1)
            if repo not in seen_repos:
                seen_repos.add(repo)
                hints["repos"].append(repo)
        if file_line := extract_file_line_hint(text):
            key = f"{file_line[0]}:{file_line[1]}"
            if key not in seen_files:
                seen_files.add(key)
                hints["file_lines"].append({"path": file_line[0], "line": file_line[1]})
        for match in _WHERE_HANDLED_RE.finditer(text):
            hints["search_terms"].append(match.group(1).strip())
        for match in _FIND_IN_RE.finditer(text):
            hints["search_terms"].append(match.group(1).strip())

    return hints


def format_session_git_context(session: Any, intent: str) -> str:
    """Compact git context block for investigation prompts."""
    parts: list[str] = []
    active = (session.metadata or {}).get("active_pr") if session else None
    if isinstance(active, dict) and active.get("repo"):
        head = active.get("head") or "?"
        parts.append(
            f"Active PR: #{active.get('number')} in `{active['repo']}` (branch `{head}`)."
        )

    last = (session.metadata or {}).get("last_git_action") if session else None
    if isinstance(last, dict) and last.get("tool"):
        parts.append(f"Last git tool: `{last['tool']}` with {last.get('args') or {}}.")

    history_texts = [intent]
    if session:
        history_texts.extend(turn.content for turn in session.turns[-6:])
    hints = collect_thread_git_hints(*history_texts)
    if hints["file_lines"]:
        cites = ", ".join(f"`{f['path']}:{f['line']}`" for f in hints["file_lines"][:5])
        parts.append(f"File references in thread: {cites}.")
    if hints["repos"] and not active:
        parts.append(f"Repos mentioned: {', '.join(f'`{r}`' for r in hints['repos'][:3])}.")

    if not parts:
        return ""
    return "## Git thread context\n" + "\n".join(f"- {p}" for p in parts)


def last_git_action_from_session(session: Any) -> tuple[str, dict[str, Any]] | None:
    if not session:
        return None
    last = (session.metadata or {}).get("last_git_action")
    if not isinstance(last, dict):
        return None
    tool = last.get("tool")
    args = last.get("args")
    if not isinstance(tool, str) or not isinstance(args, dict):
        return None
    return tool, dict(args)


def detect_investigate_direct_action(
    intent: str,
    skill_name: str,
    git: GitConfig,
    session: Any | None,
) -> tuple[str, dict[str, Any]] | None:
    """Direct local git tool when intent is unambiguous (investigate_bug / review_pr)."""
    if skill_name not in ("investigate_bug", "review_pr"):
        return None

    if session and wants_git_retry(intent):
        replay = last_git_action_from_session(session)
        if replay:
            return replay

    if session and wants_same_pr(intent) and not extract_pr_reference(intent):
        active = (session.metadata or {}).get("active_pr")
        if isinstance(active, dict) and active.get("repo") and active.get("number"):
            return "get_pr", {"repo": active["repo"], "number": int(active["number"])}

    history = session_history_texts(session, intent, limit=4)

    if match := _WHAT_USE_FOR_RE.search(intent):
        term = match.group(1).strip().rstrip("?").strip()
        if term:
            repo = _resolve_repo_from_hints(intent, git, session, history)
            if repo:
                keyword = term.split()[0] if term.split() else term
                args: dict[str, Any] = {"repo": repo, "pattern": keyword}
                ref = _session_ref(session)
                if ref:
                    args["ref"] = ref
                return "grep_repo", args

    if file_line := extract_file_line_hint(intent):
        repo = _resolve_repo_from_hints(intent, git, session, history)
        if repo:
            start = max(1, file_line[1] - 15)
            return "read_file", {
                "repo": repo,
                "path": file_line[0],
                "start_line": start,
                "end_line": file_line[1] + 15,
            }

    for text in history:
        if match := _WHERE_HANDLED_RE.search(text):
            term, repo_raw = match.group(1).strip(), match.group(2).strip()
            repo = _resolve_repo_slug(repo_raw, git)
            if repo and term:
                ref = _session_ref(session)
                args: dict[str, Any] = {"repo": repo, "pattern": re.escape(term)}
                if ref:
                    args["ref"] = ref
                return "grep_repo", args

        if match := _FIND_IN_RE.search(text):
            term, repo_raw = match.group(1).strip(), match.group(2).strip()
            repo = _resolve_repo_slug(repo_raw, git)
            if repo and term:
                args = {"repo": repo, "pattern": term}
                ref = _session_ref(session)
                if ref:
                    args["ref"] = ref
                return "grep_repo", args

    return None


def build_git_metadata_patch(
    tool_name: str,
    args: dict[str, Any],
    result: Any,
    *,
    existing_pr: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Metadata to persist after a successful git tool run."""
    patch: dict[str, Any] = {
        "last_git_action": {"tool": tool_name, "args": dict(args)},
    }

    if tool_name == "get_pr" and result.kind == "pr_detail":
        pr = result.data.get("pr") or {}
        patch["active_pr"] = {
            "repo": pr.get("repo"),
            "number": pr.get("number"),
            "head": pr.get("head"),
            "base": pr.get("base"),
            "title": pr.get("title"),
            "url": pr.get("url"),
        }
    elif existing_pr:
        patch["active_pr"] = existing_pr

    return patch


def enrich_tool_arguments(
    tool_name: str,
    arguments: dict[str, Any],
    git: GitConfig,
    session: Any | None,
) -> dict[str, Any]:
    """Fill repo/ref from session context when the model omits them."""
    args = dict(arguments)
    active = (session.metadata or {}).get("active_pr") if session else None
    ref = _session_ref(session)

    if tool_name == "get_pr":
        if isinstance(active, dict):
            if not args.get("repo") and active.get("repo"):
                args["repo"] = active["repo"]
            if args.get("number") is None and active.get("number") is not None:
                args["number"] = active["number"]

    if tool_name in _LOCAL_REPO_TOOLS and ref and not args.get("ref"):
        args["ref"] = ref

    if tool_name in _LOCAL_REPO_TOOLS | _API_REPO_TOOLS:
        repo = str(args.get("repo") or "").strip()
        history = session_history_texts(session, limit=6)
        if not repo:
            fallback = _resolve_repo_from_hints("", git, session, history)
            if fallback:
                args["repo"] = fallback
        elif repo:
            try:
                args["repo"] = resolve_repo_slug(repo, git)
            except ValueError:
                if session:
                    fallback = _resolve_repo_from_hints("", git, session, history)
                    if fallback:
                        args["repo"] = fallback

    # JIRA active ticket argument enrichment
    active_jira = (session.metadata or {}).get("active_jira_ticket") if session else None
    if active_jira and tool_name.startswith(("jira", "add_jira", "transition_jira", "get_jira", "comment_jira")):
        if not args.get("issue_key") and not args.get("key"):
            args["issue_key"] = active_jira

    return args


def metadata_patch_for_tool_result(
    tool_name: str,
    args: dict[str, Any],
    result: Any,
) -> dict[str, Any] | None:
    if result.kind == "error":
        return None
    return build_git_metadata_patch(tool_name, args, result)


def _session_ref(session: Any | None) -> str | None:
    if not session:
        return None
    active = (session.metadata or {}).get("active_pr")
    if isinstance(active, dict) and active.get("head"):
        return str(active["head"])
    last = (session.metadata or {}).get("last_git_action")
    if isinstance(last, dict):
        last_args = last.get("args") or {}
        if last_args.get("ref"):
            return str(last_args["ref"])
    return None


def _resolve_repo_slug(repo: str, git: GitConfig) -> str | None:
    try:
        return resolve_repo_slug(repo.strip(), git)
    except ValueError:
        return None


def _resolve_repo_from_hints(
    intent: str,
    git: GitConfig,
    session: Any | None,
    history: list[str],
) -> str | None:
    for text in [intent, *history]:
        if match := _REPO_IN_TEXT_RE.search(text or ""):
            slug = _resolve_repo_slug(match.group(1), git)
            if slug:
                return slug
        if ref := extract_pr_reference(text or ""):
            return ref[0]

    if session:
        for turn in session.turns[-6:]:
            content = turn.content or ""
            if match := _REPO_IN_TEXT_RE.search(content):
                slug = _resolve_repo_slug(match.group(1), git)
                if slug:
                    return slug
            if ref := extract_pr_reference(content):
                return ref[0]

    active = (session.metadata or {}).get("active_pr") if session else None
    if isinstance(active, dict) and active.get("repo"):
        return str(active["repo"])

    last = last_git_action_from_session(session) if session else None
    if last:
        repo = last[1].get("repo")
        if repo:
            try:
                return resolve_repo_slug(str(repo), git)
            except ValueError:
                return str(repo)

    if git.default_org:
        match = re.search(r"\b(?:repo(?:sitory)?|on|in)\s+([a-zA-Z0-9_.-]+)\b", intent, re.I)
        if match:
            return _resolve_repo_slug(match.group(1), git)

    if git.main_repo:
        try:
            return resolve_repo_slug(git.main_repo.strip(), git)
        except ValueError:
            raw = git.main_repo.strip().strip("/")
            if "/" in raw:
                return raw

    return None
