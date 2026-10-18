"""Intent-class reply formatters for LangGraph format_reply node."""

from __future__ import annotations

from typing import Any


def format_doc_search(data: dict[str, Any]) -> str:
    query = str(data.get("query") or "")
    results = list(data.get("results") or [])
    if not results:
        return f'No documentation found for "{query}". Try `list_repo_docs` to see indexed paths.'

    lines = [f'**Documentation search:** "{query}"', ""]
    for idx, hit in enumerate(results, start=1):
        path = str(hit.get("path") or "")
        title = str(hit.get("title") or path)
        excerpt = str(hit.get("excerpt") or "").strip()
        url = str(hit.get("url") or "").strip()
        if url:
            lines.append(f"{idx}. **{title}** — {url}")
        else:
            lines.append(f"{idx}. **`{path}`** — {title}")
        if excerpt:
            lines.append(f"   > {excerpt[:300]}")
    lines.append("")
    lines.append("_Include the public docs URL from each hit in the Slack reply._")
    return "\n".join(lines)


def format_slack_summary(data: dict[str, Any], *, intent_class: str) -> str:
    text = str(data.get("text") or "").strip()
    if text:
        return text
    messages = data.get("messages") or data.get("text")
    count = data.get("message_count")
    if count is not None:
        label = "thread" if "thread" in intent_class else "channel"
        return f"Fetched {count} messages from Slack {label}."
    return ""


_INTENT_FORMATTERS: dict[str, Any] = {
    "repo.docs.qa": lambda kind, data, raw: format_doc_search(data) if kind == "doc_search" else raw,
    "slack.summarize.thread": lambda kind, data, raw: format_slack_summary(data, intent_class="slack.summarize.thread") or raw,
    "slack.summarize.alerts": lambda kind, data, raw: format_slack_summary(data, intent_class="slack.summarize.alerts") or raw,
}


def format_reply_for_intent(
    *,
    intent_class: str,
    kind: str,
    data: dict[str, Any],
    raw_text: str,
) -> str:
    if kind == "doc_search":
        return format_doc_search(data)
    formatter = _INTENT_FORMATTERS.get(intent_class or "")
    if formatter is None:
        return ""
    return str(formatter(kind, data, raw_text) or "")
