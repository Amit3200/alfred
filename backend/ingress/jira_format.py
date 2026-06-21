"""Format JIRA tool results for Slack and UI."""

from __future__ import annotations

from backend.jira.api import JiraIssueSummary


def format_jira_issues(issues: list[JiraIssueSummary], *, slack: bool = False) -> str:
    if not issues:
        return "No JIRA issues found."
    bullet = "•" if slack else "-"
    lines = [f"*{len(issues)} issue(s)*" if slack else f"{len(issues)} issue(s):"]
    for issue in issues:
        if slack:
            lines.append(f"{bullet} <{issue.url}|{issue.key}> [{issue.status}] {issue.summary}")
        else:
            lines.append(f"{bullet} `{issue.key}` [{issue.status}] {issue.summary}")
            lines.append(f"  {issue.url}")
    return "\n".join(lines)


def format_jira_detail(detail: dict, *, slack: bool = False) -> str:
    key = str(detail.get("key") or "")
    summary = str(detail.get("summary") or "")
    status = str(detail.get("status") or "")
    url = str(detail.get("url") or "")
    issue_type = str(detail.get("issue_type") or "")
    assignee = str(detail.get("assignee") or "")
    priority = str(detail.get("priority") or "")
    description = str(detail.get("description") or "").strip()

    header = f"*{key}* — {summary}" if slack else f"`{key}` — {summary}"
    meta_parts = [part for part in [status, issue_type, priority, assignee and f"@{assignee}"] if part]
    meta = " · ".join(meta_parts)
    lines = [header, meta]
    if url:
        lines.append(f"<{url}|Open in JIRA>" if slack else url)
    if description:
        excerpt = description if len(description) <= 500 else description[:497] + "..."
        lines.append("")
        lines.append(excerpt)

    links = detail.get("remote_links") or []
    if links:
        lines.append("")
        lines.append("*Links*" if slack else "Links:")
        for link in links[:8]:
            title = str(link.get("title") or link.get("url") or "")
            link_url = str(link.get("url") or "")
            if slack and link_url:
                lines.append(f"• <{link_url}|{title}>")
            elif link_url:
                lines.append(f"- {title}: {link_url}")

    issue_links = detail.get("links") or []
    if issue_links:
        lines.append("")
        lines.append("*Related issues*" if slack else "Related issues:")
        for link in issue_links[:8]:
            rel = str(link.get("relationship") or "relates to")
            linked_key = str(link.get("key") or "")
            linked_summary = str(link.get("summary") or "")
            lines.append(f"- {rel}: `{linked_key}` {linked_summary}".strip())

    return "\n".join(lines)


def format_jira_action(action: str, data: dict, *, slack: bool = False) -> str:
    key = str(data.get("key") or "")
    url = str(data.get("url") or data.get("issue_url") or "")
    if action == "transition":
        status = str(data.get("status") or "")
        transition = str(data.get("transition") or "")
        msg = f"Moved `{key}` via {transition} → *{status}*"
    elif action == "comment":
        msg = f"Added comment to `{key}`."
    elif action == "link":
        title = str(data.get("title") or data.get("url") or "")
        msg = f"Linked `{key}` to {title}."
    elif action == "update":
        fields = ", ".join(data.get("updated_fields") or [])
        msg = f"Updated `{key}`" + (f" ({fields})" if fields else "") + "."
    elif action == "create":
        msg = f"Created `{key}` — {data.get('summary') or 'new issue'}."
    else:
        msg = f"Updated `{key}`."
    if slack and url:
        return f"{msg}\n<{url}|Open in JIRA>"
    if url:
        return f"{msg}\n{url}"
    return msg
