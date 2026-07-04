from __future__ import annotations
from backend.integrations.slack.sanitize import clean_slack_text
from backend.integrations.jira.api import extract_issue_key


import re
from typing import Any

from backend.integrations.slack.sanitize import extract_slack_mention_labels, extract_slack_user_ids, clean_slack_text
from backend.integrations.jira.api import JiraApiClient, extract_issue_key
from backend.models.config import AlfredConfig, JiraConfig
from backend.models.task import Task
from backend.db.slack_user_cache import SlackUserCache
from backend.integrations.slack.users import pick_slack_display_name
from slack_sdk import WebClient

_ASSIGNED_TO_RE = re.compile(
    r"\bassigned to\s+(.+?)(?:\?|$|\s+(?:which|in|from|for)\b)",
    re.I,
)
_MY_ASSIGNED_RE = re.compile(
    r"\b(my|mine|me)\b.*\b(task|ticket|issue|jira|assigned)\b|\bassigned to me\b",
    re.I,
)
_OPEN_HINTS = ("open", "not done", "not closed", "in progress", "active")
_LIST_HINTS = (
    "list",
    "show",
    "get",
    "give me",
    "find",
    "search",
    "what are",
    "all the",
    "all open",
    "open tickets",
)

_DEFAULT_CLOSED_STATUSES = ("Done", "Closed", "Resolved", "Cancelled")


def jira_project_keys(config: JiraConfig) -> list[str]:
    if config.allowed_projects:
        return [p.strip().upper() for p in config.allowed_projects if p.strip()]
    if config.default_project.strip():
        return [config.default_project.strip().upper()]
    return []


def format_jira_context_for_prompt(
    config: AlfredConfig,
    task: Task,
    session: Any | None = None,
    *,
    data_dir: Any | None = None,
) -> str:
    """Inject JIRA site defaults and resolved assignees into the system prompt."""
    jira = config.jira
    if not jira.enabled:
        return ""

    parts: list[str] = [
        "## JIRA context",
        f"- Site: `{jira.base_url.rstrip('/')}`",
        f"- API user: `{jira.email}`",
    ]
    active_ticket = (session.metadata or {}).get("active_jira_ticket") if session else None
    if active_ticket:
        parts.append(f"- Active JIRA ticket: `{active_ticket}` (referenced in thread context)")

    projects = jira_project_keys(jira)
    if projects:
        parts.append(f"- Default project scope: {', '.join(f'`{p}`' for p in projects)}")
    if jira.assignee_map:
        mapped = ", ".join(f"`{k}` → `{v}`" for k, v in list(jira.assignee_map.items())[:8])
        parts.append(f"- Known assignee mappings: {mapped}")

    try:
        client = JiraApiClient.from_alfred_config(config)
    except RuntimeError:
        parts.append("- JIRA token not configured — tools will fail until Secrets are set.")
        return "\n".join(parts)

    assignees = resolve_assignees_for_task(task, config, client, data_dir=data_dir)
    if assignees:
        parts.append(
            "- Resolved assignee(s) for this request: "
            + ", ".join(f"`{a}`" for a in assignees)
        )
        parts.append(
            "- Use these in JQL (`assignee = \"email@…\"`) — do **not** substitute `currentUser()` "
            "unless the user explicitly asked for their own tasks."
        )
    elif wants_current_user(task.cleaned_intent):
        parts.append("- User asked for **their own** tasks — JQL may use `assignee = currentUser()`.")

    if _looks_like_open_list(task.cleaned_intent) and projects:
        sample = build_open_assigned_jql(
            assignees or (["currentUser()"] if wants_current_user(task.cleaned_intent) else []),
            projects,
        )
        if sample:
            parts.append(f"- Suggested JQL for this list query: `{sample}`")

    history = [task.cleaned_intent]
    if session:
        history.extend(turn.content for turn in session.turns[-4:])
    for text in history:
        if key := _extract_issue_key(text):
            parts.append(f"- Issue key in thread: `{key}`.")
            break

    return "\n".join(parts)


def resolve_assignees_for_task(
    task: Task,
    config: AlfredConfig,
    client: JiraApiClient | None = None,
    *,
    data_dir: Any | None = None,
) -> list[str]:
    """Resolve JIRA assignee identifiers (email preferred) from Slack mentions and names."""
    if wants_current_user(task.cleaned_intent) and not _has_other_assignee_hint(task):
        return []

    client = client or JiraApiClient.from_alfred_config(config)
    seen: set[str] = set()
    resolved: list[str] = []

    def add(candidate: str) -> None:
        value = resolve_jira_assignee(candidate, config, client)
        if value and value not in seen:
            seen.add(value)
            resolved.append(value)

    labels = extract_slack_mention_labels(task.raw_text)

    for user_id in extract_slack_user_ids(task.raw_text):
        if user_id == (task.user_id or ""):
            continue
        display = labels.get(user_id) or _slack_display_name(user_id, config, data_dir)
        if display:
            add(display)
        elif user_id in config.jira.assignee_map:
            add(user_id)

    if match := _ASSIGNED_TO_RE.search(task.cleaned_intent):
        name = match.group(1).strip().strip("?.!")
        if name and name.lower() not in {"me", "myself", "mine"}:
            add(name)

    for name in _names_from_raw_text(task.raw_text):
        add(name)

    return resolved


def resolve_jira_assignee(name_or_id: str, config: AlfredConfig, client: JiraApiClient) -> str | None:
    key = (name_or_id or "").strip()
    if not key:
        return None

    mapped = config.jira.assignee_map.get(key) or config.jira.assignee_map.get(key.lower())
    if mapped:
        return mapped.strip()

    if "@" in key and "." in key:
        return key

    for label, value in config.jira.assignee_map.items():
        if label.lower() == key.lower():
            return value.strip()

    try:
        users = client.search_users(key, max_results=8)
    except RuntimeError:
        return key if "@" in key else None

    if not users:
        return None

    needle = key.lower()
    for user in users:
        display = str(user.get("displayName") or "").lower()
        email = str(user.get("emailAddress") or "")
        if display == needle or needle in display:
            return email or str(user.get("accountId") or "") or None

    first = users[0]
    return str(first.get("emailAddress") or first.get("accountId") or "") or None


def build_open_assigned_jql(assignees: list[str], project_keys: list[str]) -> str:
    parts: list[str] = []
    if project_keys:
        if len(project_keys) == 1:
            parts.append(f'project = "{project_keys[0]}"')
        else:
            quoted = ", ".join(f'"{key}"' for key in project_keys)
            parts.append(f"project in ({quoted})")

    closed = ", ".join(f'"{status}"' for status in _DEFAULT_CLOSED_STATUSES)
    parts.append(f"status not in ({closed})")

    if assignees:
        if len(assignees) == 1 and assignees[0] == "currentUser()":
            parts.append("assignee = currentUser()")
        elif len(assignees) == 1:
            parts.append(f'assignee = "{assignees[0]}"')
        else:
            quoted = ", ".join(
                "currentUser()" if a == "currentUser()" else f'"{a}"' for a in assignees
            )
            parts.append(f"assignee in ({quoted})")

    return " AND ".join(parts) + " ORDER BY updated DESC"


def detect_jira_list_action(
    intent: str,
    config: AlfredConfig,
    task: Task | None = None,
    *,
    data_dir: Any | None = None,
) -> tuple[str, dict[str, Any]] | None:
    """Direct jira_search when intent is a list/filter query."""
    if not config.jira.enabled or task is None:
        return None

    from backend.integrations.identity.user_identity import is_user_identity_lookup
    if is_user_identity_lookup(intent):
        return None

    lower = intent.lower()
    if not any(h in lower for h in _LIST_HINTS):
        return None
    ticket_context = (*_OPEN_HINTS, "assigned", "ticket", "task", "issue", "sprint", "backlog")
    if not any(h in lower for h in ticket_context):
        return None

    try:
        client = JiraApiClient.from_alfred_config(config)
    except RuntimeError:
        return None

    assignees = resolve_assignees_for_task(task, config, client, data_dir=data_dir)
    if not assignees and wants_current_user(intent):
        assignees = ["currentUser()"]

    projects = jira_project_keys(config.jira)
    if assignees or (projects and _looks_like_open_list(intent)):
        jql = build_open_assigned_jql(assignees, projects)
        return "jira_search", {"jql": jql, "max_results": 50}
    return None


def wants_current_user(intent: str) -> bool:
    return bool(_MY_ASSIGNED_RE.search(intent or ""))


def _looks_like_open_list(intent: str) -> bool:
    lower = (intent or "").lower()
    return any(h in lower for h in _LIST_HINTS) and any(
        h in lower for h in (*_OPEN_HINTS, "assigned", "jira", "ticket")
    )


def _has_other_assignee_hint(task: Task) -> bool:
    if extract_slack_user_ids(task.raw_text):
        ids = extract_slack_user_ids(task.raw_text)
        return any(uid != (task.user_id or "") for uid in ids)
    if _ASSIGNED_TO_RE.search(task.cleaned_intent):
        name = _ASSIGNED_TO_RE.search(task.cleaned_intent).group(1).strip().lower()
        return name not in {"me", "myself", "mine", ""}
    return bool(_names_from_raw_text(task.raw_text))


def _slack_display_name(user_id: str, config: AlfredConfig, data_dir: Any | None) -> str | None:
    if data_dir is not None:
        cached = SlackUserCache(data_dir).get(user_id)
        if cached:
            return cached

    if not config.slack.enabled or not config.slack.bot_token:
        return None

    try:
        client = WebClient(token=config.slack.bot_token)
        response = client.users_info(user=user_id)
        return pick_slack_display_name(response.get("user") or {})
    except Exception:
        return None


def _names_from_raw_text(raw_text: str) -> list[str]:
    """Best-effort display names left in raw Slack text after stripping bot mention."""


    cleaned = clean_slack_text(raw_text)
    if match := _ASSIGNED_TO_RE.search(cleaned):
        name = match.group(1).strip().strip("?.!")
        if name and name.lower() not in {"me", "myself", "mine"}:
            return [name]
    return []


def _extract_issue_key(text: str) -> str | None:


    return extract_issue_key(text)
