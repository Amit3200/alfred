"""Slack ↔ JIRA user identity lookup — build assignee maps for efficient searches."""

from __future__ import annotations

import re
from typing import Any

from backend.ingress.jira_context import resolve_jira_assignee
from backend.ingress.sanitize import extract_slack_mention_labels, extract_slack_user_ids
from backend.jira.api import JiraApiClient
from backend.models.config import AlfredConfig
from backend.models.task import Task

_IDENTITY_FIELD_MARKERS = (
    "slack email",
    "slack handle",
    "jira email",
    "jira name",
    "email_id",
    "email id",
    "slack id",
    "user id",
    "account id",
    "tagged",
    "mention",
    "handle",
    "username",
)

_IDENTITY_ACTION_MARKERS = (
    "map",
    "mapping",
    "mapped",
    "assignee map",
    "user map",
    "identity",
    "cross-reference",
    "cross reference",
)

_NAME_OF_PERSON_RE = re.compile(
    r"\b(?:name of|for|about)\s+(?:person|user|member|employee)?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
    re.I,
)

_WORKSPACE_MARKERS = (
    "all users",
    "all slack",
    "all members",
    "all people",
    "everyone",
    "whole workspace",
    "full workspace",
    "workspace map",
    "entire workspace",
    "whole team",
    "all teammates",
    "every member",
)

_BOT_LABELS = frozenset({"alfred", "slackbot"})


def is_workspace_identity_request(intent: str) -> bool:
    """True when the user wants a bulk Slack workspace identity map."""
    lower = (intent or "").lower()
    if any(marker in lower for marker in _WORKSPACE_MARKERS):
        return True
    if "all" in lower and any(
        word in lower for word in ("slack", "user", "member", "people", "team", "workspace")
    ):
        if any(word in lower for word in ("map", "identity", "jira", "github", "email", "assignee")):
            return True
    return False


def is_user_identity_lookup(intent: str) -> bool:
    """True when the user wants Slack/JIRA identity fields, not ticket search."""
    if is_workspace_identity_request(intent):
        return True
    lower = (intent or "").lower()
    has_slack = "slack" in lower
    has_jira = "jira" in lower
    has_field = any(marker in lower for marker in _IDENTITY_FIELD_MARKERS)
    has_action = any(marker in lower for marker in _IDENTITY_ACTION_MARKERS)
    if has_slack and has_jira and (has_field or has_action):
        return True
    if has_action and (has_slack or has_jira) and has_field:
        return True
    if "name of person" in lower and (has_slack or has_jira):
        return True
    return False


def detect_user_identity_action(
    intent: str,
    config: AlfredConfig,
    task: Task | None = None,
    *,
    session: Any | None = None,
    data_dir: Any | None = None,
) -> tuple[str, dict[str, Any]] | None:
    if task is None:
        return None
    if not is_user_identity_lookup(intent):
        return None
    if is_workspace_identity_request(intent):
        return "build_workspace_identity_map", {"include_github": "github" in intent.lower()}

    if not config.jira.enabled and not config.slack.enabled:
        return None

    targets = collect_identity_targets(task, session)
    if not targets:
        name = _name_from_intent(intent)
        if name:
            targets = [{"query": name}]
    if not targets:
        return "lookup_user_identity", {}
    if len(targets) == 1:
        target = targets[0]
        return "lookup_user_identity", {
            k: v for k, v in target.items() if k in ("slack_user_id", "query")
        }
    return "lookup_user_identity", {"targets": targets}


def collect_identity_targets(task: Task, session: Any | None = None) -> list[dict[str, str]]:
    """Gather Slack user IDs or name queries from the message and recent thread."""
    seen: set[str] = set()
    targets: list[dict[str, str]] = []

    def add(*, slack_user_id: str = "", query: str = "") -> None:
        key = slack_user_id or query.strip().lower()
        if not key or key in seen:
            return
        seen.add(key)
        entry: dict[str, str] = {}
        if slack_user_id:
            entry["slack_user_id"] = slack_user_id
        if query:
            entry["query"] = query
        targets.append(entry)

    labels = extract_slack_mention_labels(task.raw_text)
    for user_id in extract_slack_user_ids(task.raw_text):
        if user_id == (task.user_id or ""):
            continue
        label = labels.get(user_id, "")
        if label.strip().lower() in _BOT_LABELS:
            continue
        add(slack_user_id=user_id, query=label)

    texts = [task.raw_text]
    if session is not None:
        texts.extend(turn.content for turn in session.turns[-8:])

    for text in texts:
        thread_labels = extract_slack_mention_labels(text)
        for user_id in extract_slack_user_ids(text):
            if user_id == (task.user_id or ""):
                continue
            label = thread_labels.get(user_id, "")
            if label.strip().lower() in _BOT_LABELS:
                continue
            add(slack_user_id=user_id, query=label)

    return targets


def build_workspace_identity_map(
    config: AlfredConfig,
    *,
    data_dir: Any | None = None,
    include_github: bool = True,
) -> dict[str, Any]:
    """Map every human Slack workspace member to JIRA and optionally GitHub."""
    slack_client = _slack_client(config)
    if slack_client is None:
        return {"error": "Slack is not configured — enable Slack and set the bot token."}

    members, list_error = list_slack_human_members(slack_client)
    if list_error:
        return {"error": list_error}
    if not members:
        return {"error": "No human Slack members found in the workspace."}

    jira_client: JiraApiClient | None = None
    if config.jira.enabled:
        try:
            jira_client = JiraApiClient.from_alfred_config(config)
        except RuntimeError as exc:
            return {"error": str(exc)}

    github_members: list[dict[str, Any]] = []
    if include_github and config.git.enabled and config.git.token and config.git.default_org:
        try:
            from backend.git.api import GitApiClient

            github_members = GitApiClient.from_alfred_config(config).list_org_members()
        except Exception:
            github_members = []

    entries: list[dict[str, Any]] = []
    for member in members:
        entry = _resolve_slack_member(config, jira_client, member, data_dir=data_dir)
        if github_members:
            entry["github_login"] = _match_github_login(entry, github_members)
        entries.append(entry)

    matched_jira = sum(1 for entry in entries if entry.get("jira_email"))
    matched_github = sum(1 for entry in entries if entry.get("github_login"))

    return {
        "workspace": True,
        "count": len(entries),
        "matched_jira": matched_jira,
        "matched_github": matched_github,
        "identities": entries,
        "assignee_map_suggestion": _assignee_map_suggestion(entries),
    }


def list_slack_human_members(
    slack_client: Any,
) -> tuple[list[dict[str, Any]], str | None]:
    """Return active non-bot Slack members from users.list."""
    from backend.ingress.slack_users import pick_slack_display_name

    bot_ids = _slack_bot_user_ids(slack_client)
    members: list[dict[str, Any]] = []
    cursor: str | None = None
    try:
        while True:
            response = slack_client.users_list(limit=200, cursor=cursor)
            if not response.get("ok"):
                return [], f"Slack users.list failed: {response.get('error') or 'unknown error'}"
            for member in response.get("members") or []:
                user_id = str(member.get("id") or "")
                if not user_id or user_id in bot_ids:
                    continue
                if member.get("deleted") or member.get("is_bot"):
                    continue
                if pick_slack_display_name(member).lower() in _BOT_LABELS:
                    continue
                members.append(member)
            cursor = (response.get("response_metadata") or {}).get("next_cursor") or None
            if not cursor:
                break
    except Exception as exc:
        return [], f"Slack users.list failed: {exc}"

    members.sort(key=lambda member: pick_slack_display_name(member).lower())
    return members, None


def lookup_user_identity(
    config: AlfredConfig,
    *,
    task: Task | None = None,
    data_dir: Any | None = None,
    slack_user_id: str = "",
    query: str = "",
    targets: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Resolve Slack profile + JIRA user for one or more people."""
    entries: list[dict[str, Any]] = []
    todo = _normalize_targets(slack_user_id=slack_user_id, query=query, targets=targets)
    if not todo and task is not None:
        todo = collect_identity_targets(task)
    if not todo:
        return {
            "error": (
                "Please @mention the person in Slack (or give their name) "
                "so I can map Slack ↔ JIRA identity fields."
            )
        }

    try:
        jira_client = JiraApiClient.from_alfred_config(config)
    except RuntimeError as exc:
        return {"error": str(exc)}

    slack_client = _slack_client(config)
    for target in todo:
        entry = _resolve_one_identity(
            config,
            jira_client,
            slack_client,
            data_dir=data_dir,
            slack_user_id=target.get("slack_user_id", ""),
            query=target.get("query", ""),
        )
        entries.append(entry)

    return {
        "identities": entries,
        "assignee_map_suggestion": _assignee_map_suggestion(entries),
    }


def format_user_identity_result(data: dict[str, Any]) -> str:
    if message := data.get("error"):
        return str(message)

    if data.get("workspace"):
        return _format_workspace_identity_result(data)

    lines: list[str] = ["*Slack ↔ JIRA identity map*"]
    for entry in data.get("identities") or []:
        lines.append("")
        lines.append(f"*{entry.get('display_name') or entry.get('query') or 'User'}*")
        lines.append(f"• Slack user ID: `{entry.get('slack_user_id') or '—'}`")
        lines.append(f"• Slack name: {entry.get('slack_display_name') or '—'}")
        lines.append(f"• Slack real name: {entry.get('slack_real_name') or '—'}")
        lines.append(f"• Slack email: {entry.get('slack_email') or '—'}")
        lines.append(f"• Slack handle (tag as): `<@{entry.get('slack_user_id')}>`")
        lines.append(f"• JIRA display name: {entry.get('jira_display_name') or '—'}")
        lines.append(f"• JIRA email: {entry.get('jira_email') or '—'}")
        lines.append(f"• JIRA account ID: `{entry.get('jira_account_id') or '—'}`")

    suggestion = data.get("assignee_map_suggestion") or {}
    if suggestion:
        lines.append("")
        lines.append("*Suggested `jira.assignee_map` entries (add to `.alfred/config.yaml`):*")
        lines.append("```yaml")
        lines.append("jira:")
        lines.append("  assignee_map:")
        for key, value in suggestion.items():
            lines.append(f'    "{key}": {value}')
        lines.append("```")

    return "\n".join(lines)


def _normalize_targets(
    *,
    slack_user_id: str,
    query: str,
    targets: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    if targets:
        return [t for t in targets if t.get("slack_user_id") or t.get("query")]
    if slack_user_id or query:
        return [{"slack_user_id": slack_user_id, "query": query}]
    return []


def _resolve_slack_member(
    config: AlfredConfig,
    jira_client: JiraApiClient | None,
    member: dict[str, Any],
    *,
    data_dir: Any | None,
) -> dict[str, Any]:
    from backend.ingress.slack_users import pick_slack_display_name

    slack_profile = member.get("profile") or {}
    user_id = str(member.get("id") or "")
    entry: dict[str, Any] = {
        "slack_user_id": user_id,
        "slack_display_name": pick_slack_display_name(member),
        "slack_real_name": str(member.get("real_name") or slack_profile.get("real_name") or ""),
        "slack_email": str(slack_profile.get("email") or ""),
        "slack_handle": str(member.get("name") or ""),
    }
    if data_dir is not None and entry.get("slack_display_name"):
        from backend.storage.slack_user_cache import SlackUserCache

        SlackUserCache(data_dir).remember(user_id, str(entry["slack_display_name"]))

    if jira_client is None:
        entry["display_name"] = entry["slack_display_name"] or entry["slack_real_name"] or user_id
        return entry

    search_name = entry["slack_display_name"] or entry["slack_real_name"] or user_id
    jira_email = resolve_jira_assignee(str(search_name), config, jira_client)
    if not jira_email and entry.get("slack_email"):
        jira_email = resolve_jira_assignee(str(entry["slack_email"]), config, jira_client)

    jira_user = _pick_jira_user(jira_client, str(search_name), jira_email)
    if jira_user:
        entry["jira_display_name"] = jira_user.get("displayName") or ""
        entry["jira_email"] = jira_user.get("emailAddress") or jira_email or ""
        entry["jira_account_id"] = jira_user.get("accountId") or ""
    else:
        entry["jira_email"] = jira_email or ""
        entry["jira_display_name"] = ""
        entry["jira_account_id"] = ""

    entry["display_name"] = (
        entry.get("slack_display_name")
        or entry.get("slack_real_name")
        or entry.get("jira_display_name")
        or user_id
    )
    return entry


def _format_workspace_identity_result(data: dict[str, Any]) -> str:
    count = int(data.get("count") or 0)
    matched_jira = int(data.get("matched_jira") or 0)
    matched_github = int(data.get("matched_github") or 0)
    lines: list[str] = [
        f"*Workspace identity map* ({count} people)",
        f"JIRA matched: {matched_jira}/{count} · GitHub matched: {matched_github}/{count}",
        "",
    ]
    for entry in data.get("identities") or []:
        name = entry.get("display_name") or entry.get("slack_display_name") or "Unknown"
        slack_email = entry.get("slack_email") or "—"
        jira_email = entry.get("jira_email") or "—"
        github = entry.get("github_login") or "—"
        slack_id = entry.get("slack_user_id") or "—"
        handle = entry.get("slack_handle") or "—"
        lines.append(
            f"• *{name}* — slack `{slack_id}` @{handle} · {slack_email} · "
            f"jira {jira_email} · github `{github}`"
        )

    suggestion = data.get("assignee_map_suggestion") or {}
    if suggestion:
        lines.extend(["", "*Suggested `jira.assignee_map` (paste into `.alfred/config.yaml`):*", "```yaml"])
        lines.append("jira:")
        lines.append("  assignee_map:")
        for key, value in suggestion.items():
            lines.append(f'    "{key}": {value}')
        lines.append("```")

    return "\n".join(lines)


def _match_github_login(entry: dict[str, Any], org_members: list[dict[str, Any]]) -> str:
    by_login = {
        str(member.get("login") or "").lower(): str(member.get("login") or "")
        for member in org_members
        if member.get("login")
    }
    if not by_login:
        return ""

    handle = str(entry.get("slack_handle") or "").strip().lower()
    if handle and handle in by_login:
        return by_login[handle]

    email = str(entry.get("slack_email") or entry.get("jira_email") or "").strip().lower()
    if email:
        prefix = email.split("@", 1)[0]
        if prefix in by_login:
            return by_login[prefix]
        for login_lower, login in by_login.items():
            if login_lower.replace("-", "") == prefix.replace(".", "").replace("-", ""):
                return login

    display = str(entry.get("slack_display_name") or entry.get("slack_real_name") or "").lower()
    if display:
        compact = display.replace(" ", "").replace("-", "")
        hyphenated = display.replace(" ", "-")
        for candidate in (hyphenated, compact):
            if candidate in by_login:
                return by_login[candidate]

    return ""


def _slack_bot_user_ids(slack_client: Any) -> set[str]:
    bot_ids = {"USLACKBOT"}
    try:
        auth = slack_client.auth_test()
        if auth.get("ok") and auth.get("user_id"):
            bot_ids.add(str(auth["user_id"]))
    except Exception:
        pass
    return bot_ids


def _resolve_one_identity(
    config: AlfredConfig,
    jira_client: JiraApiClient,
    slack_client: Any | None,
    *,
    data_dir: Any | None,
    slack_user_id: str,
    query: str,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "slack_user_id": slack_user_id,
        "query": query,
    }

    profile = _fetch_slack_profile(config, slack_client, slack_user_id, query, data_dir)
    entry.update(profile)

    search_name = (
        profile.get("slack_display_name")
        or profile.get("slack_real_name")
        or query
        or slack_user_id
    )
    jira_email = resolve_jira_assignee(str(search_name), config, jira_client)
    if not jira_email and profile.get("slack_email"):
        jira_email = resolve_jira_assignee(str(profile["slack_email"]), config, jira_client)

    jira_user = _pick_jira_user(jira_client, str(search_name), jira_email)
    if jira_user:
        entry["jira_display_name"] = jira_user.get("displayName") or ""
        entry["jira_email"] = jira_user.get("emailAddress") or jira_email or ""
        entry["jira_account_id"] = jira_user.get("accountId") or ""
    else:
        entry["jira_email"] = jira_email or ""
        entry["jira_display_name"] = ""
        entry["jira_account_id"] = ""

    entry["display_name"] = (
        entry.get("slack_display_name")
        or entry.get("slack_real_name")
        or entry.get("jira_display_name")
        or query
        or slack_user_id
    )
    return entry


def _fetch_slack_profile(
    config: AlfredConfig,
    slack_client: Any | None,
    slack_user_id: str,
    query: str,
    data_dir: Any | None,
) -> dict[str, str]:
    from backend.ingress.slack_users import pick_slack_display_name

    profile: dict[str, str] = {}
    user_id = slack_user_id.strip()
    if not user_id and query and slack_client is not None:
        user_id = _find_slack_user_by_name(slack_client, query) or ""

    if user_id:
        profile["slack_user_id"] = user_id
        user = _slack_users_info(slack_client, user_id)
        if user:
            slack_profile = user.get("profile") or {}
            profile["slack_display_name"] = pick_slack_display_name(user)
            profile["slack_real_name"] = str(user.get("real_name") or slack_profile.get("real_name") or "")
            profile["slack_email"] = str(slack_profile.get("email") or "")
            profile["slack_handle"] = str(user.get("name") or "")
            if data_dir is not None and profile.get("slack_display_name"):
                from backend.storage.slack_user_cache import SlackUserCache

                SlackUserCache(data_dir).remember(user_id, profile["slack_display_name"])
    elif query:
        profile["query"] = query.strip()

    return profile


def _pick_jira_user(
    client: JiraApiClient,
    search_name: str,
    resolved_email: str | None,
) -> dict[str, Any] | None:
    needle = (search_name or resolved_email or "").strip()
    if not needle:
        return None
    try:
        users = client.search_users(needle, max_results=10)
    except RuntimeError:
        return None
    if not users:
        return None

    if resolved_email:
        for user in users:
            if str(user.get("emailAddress") or "").lower() == resolved_email.lower():
                return user

    lower = needle.lower()
    for user in users:
        display = str(user.get("displayName") or "").lower()
        if display == lower or lower in display:
            return user
    return users[0]


def _assignee_map_suggestion(entries: list[dict[str, Any]]) -> dict[str, str]:
    suggestion: dict[str, str] = {}
    for entry in entries:
        email = str(entry.get("jira_email") or entry.get("slack_email") or "").strip()
        if not email:
            continue
        slack_id = str(entry.get("slack_user_id") or "").strip()
        display = str(
            entry.get("slack_display_name")
            or entry.get("slack_real_name")
            or entry.get("jira_display_name")
            or entry.get("query")
            or ""
        ).strip()
        if display:
            suggestion[display] = email
        if slack_id:
            suggestion[slack_id] = email
    return suggestion


def _slack_client(config: AlfredConfig) -> Any | None:
    if not config.slack.enabled or not config.slack.bot_token:
        return None
    try:
        from slack_sdk import WebClient

        return WebClient(token=config.slack.bot_token)
    except Exception:
        return None


def _slack_users_info(client: Any | None, user_id: str) -> dict[str, Any] | None:
    if client is None or not user_id:
        return None
    try:
        response = client.users_info(user=user_id)
        if response.get("ok"):
            return response.get("user") or {}
    except Exception:
        return None
    return None


def _find_slack_user_by_name(client: Any, query: str) -> str | None:
    from backend.ingress.slack_users import pick_slack_display_name

    needle = query.strip().lower()
    if not needle:
        return None
    cursor: str | None = None
    try:
        while True:
            response = client.users_list(limit=200, cursor=cursor)
            if not response.get("ok"):
                break
            for member in response.get("members") or []:
                if member.get("deleted") or member.get("is_bot"):
                    continue
                display = pick_slack_display_name(member).lower()
                real = str((member.get("profile") or {}).get("real_name") or "").lower()
                username = str(member.get("name") or "").lower()
                if needle in {display, real, username} or needle in display or needle in real:
                    return str(member.get("id") or "") or None
            cursor = (response.get("response_metadata") or {}).get("next_cursor") or None
            if not cursor:
                break
    except Exception:
        return None
    return None


def _name_from_intent(intent: str) -> str | None:
    if match := _NAME_OF_PERSON_RE.search(intent or ""):
        return match.group(1).strip()
    return None
