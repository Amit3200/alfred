from __future__ import annotations

import abc
import re
from collections import defaultdict
from typing import Any, Callable

from backend.integrations.git.api import PullRequestSummary
from backend.integrations.jira.api import JiraIssueSummary

# Regexes for channel formatters
_DOUBLE_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_MD_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
_TABLE_ROW_RE = re.compile(r"^\s*\|(.+?)\|?\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|[\s:\-|]+\|?\s*$")
_TABLE_TITLE_RE = re.compile(r"^alert summary table\b", re.I)
_FENCE_RE = re.compile(r"^```")
_BACKTICK_PIPE_RE = re.compile(r"^`([^`|]+(?:\s*\|\s*[^`|]+)+)`$")

_SLACK_LINK_RE = re.compile(r"<([^|>\s]+)\|([^>]+)>")
_SLACK_BOLD_RE = re.compile(r"(?<!\*)\*(?!\*)([^*\n]+?)(?<!\*)\*(?!\*)")
_REPO_LINE_RE = re.compile(r"^`([^`]+)`$")
_PR_BULLET_RE = re.compile(r"^[•\-]\s*(#\d+\s+.+?)(?:\s*[—–-]\s+(https://\S+))?\s*$")
_PR_PLAIN_RE = re.compile(r"^(#\d+\s+.+?)\s*[—–-]\s+(https://\S+)\s*$")

_GITHUB_PR_URL_RE = re.compile(
    r"^(\s*(?:[-*•]\s*)?)(https://github\.com/[^/\s]+/[^/\s]+/pull/(\d+)(?:\s|$))",
    re.MULTILINE,
)


class FormatterStrategy(abc.ABC):
    """Abstract base class for all kind-specific payload rendering strategies."""

    @abc.abstractmethod
    def render(self, data: dict[str, Any], *, slack: bool = False) -> str:
        """Render raw data dictionary into a formatted string."""
        pass


# Helper for table formatting shared across strategies
def _format_table(
    columns: list[str],
    rows: list[dict[str, Any]],
    *,
    slack: bool = False,
    max_rows: int = 20,
) -> str:
    shown = rows[:max_rows]
    widths = {col: min(len(col), 24) for col in columns}
    for row in shown:
        for col in columns:
            value = str(row.get(col) or "")
            widths[col] = min(max(widths[col], min(len(value), 48)), 48)

    header = " | ".join(col[: widths[col]].ljust(widths[col]) for col in columns)
    divider = "-+-".join("-" * widths[col] for col in columns)
    body_lines = []
    for row in shown:
        cells = []
        for col in columns:
            value = str(row.get(col) or "")
            if len(value) > widths[col]:
                value = value[: widths[col] - 1] + "…"
            cells.append(value.ljust(widths[col]))
        body_lines.append(" | ".join(cells))

    table = "\n".join([header, divider, *body_lines])
    if len(rows) > max_rows:
        table += f"\n… and {len(rows) - max_rows} more row(s)"
    return f"```\n{table}\n```"


# 1. AWS Formatters
class AthenaQueryFormatter(FormatterStrategy):
    def render(self, data: dict[str, Any], *, slack: bool = False) -> str:
        columns = [str(col) for col in data.get("columns") or []]
        rows = data.get("rows") or []
        row_count = int(data.get("row_count") or len(rows))
        database = str(data.get("database") or "")
        execution_id = str(data.get("query_execution_id") or "")
        bytes_scanned = int(data.get("bytes_scanned") or 0)

        header = f"*Athena* `{database}` — {row_count} row(s)" if slack else f"Athena `{database}` — {row_count} row(s)"
        meta_parts = []
        if bytes_scanned:
            mb = bytes_scanned / (1024 * 1024)
            meta_parts.append(f"scanned {mb:.2f} MB")
        if execution_id:
            meta_parts.append(f"id `{execution_id}`")
        lines = [header]
        if meta_parts:
            lines.append(" · ".join(meta_parts))

        if not rows:
            lines.append("No rows returned.")
            return "\n".join(lines)

        if columns:
            lines.append("")
            lines.append(_format_table(columns, rows, slack=slack, max_rows=20))
        return "\n".join(lines)


class CloudWatchQueryFormatter(FormatterStrategy):
    def render(self, data: dict[str, Any], *, slack: bool = False) -> str:
        log_group = str(data.get("log_group") or "")
        rows = data.get("rows") or []
        row_count = int(data.get("row_count") or len(rows))
        start = str(data.get("start_time") or "")
        end = str(data.get("end_time") or "")

        header = f"*CloudWatch Logs* `{log_group}` — {row_count} row(s)" if slack else f"CloudWatch Logs `{log_group}` — {row_count} row(s)"
        lines = [header]
        if start and end:
            lines.append(f"{start} → {end}")

        if not rows:
            lines.append("No log events matched.")
            return "\n".join(lines)

        columns = [str(col) for col in data.get("columns") or list(rows[0].keys())]
        lines.append("")
        lines.append(_format_table(columns, rows, slack=slack, max_rows=25))
        return "\n".join(lines)


class CloudWatchLogGroupsFormatter(FormatterStrategy):
    def render(self, data: dict[str, Any], *, slack: bool = False) -> str:
        groups = [str(g) for g in data.get("groups") or []]
        prefix = str(data.get("prefix") or "")
        if not groups:
            target = prefix or "search"
            return f"No CloudWatch log groups matched `{target}`."
        bullet = "•" if slack else "-"
        title = f"*{len(groups)} log group(s)*" if slack else f"{len(groups)} log group(s):"
        lines = [title]
        for group in groups:
            lines.append(f"{bullet} `{group}`")
        return "\n".join(lines)


class WebSearchFormatter(FormatterStrategy):
    def render(self, data: dict[str, Any], *, slack: bool = False) -> str:
        query = str(data.get("query") or "")
        provider = str(data.get("provider") or "web")
        results = list(data.get("results") or [])
        answer = str(data.get("answer") or "").strip()
        lines: list[str] = []
        title = f"*Web search* ({provider}) — `{query}`" if slack else f"Web search ({provider}) — {query}"
        lines.append(title)
        if answer:
            lines.append(f"*Summary:* {answer}" if slack else f"Summary: {answer}")
        if not results:
            lines.append("No results returned.")
            return "\n".join(lines)
        bullet = "•" if slack else "-"
        for index, item in enumerate(results[:8], start=1):
            if not isinstance(item, dict):
                continue
            item_title = str(item.get("title") or "Untitled").strip()
            url = str(item.get("url") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            if slack and url:
                head = f"{bullet} <{url}|{item_title}>"
            elif url:
                head = f"{bullet} [{item_title}]({url})"
            else:
                head = f"{bullet} {item_title}"
            lines.append(head)
            if snippet:
                lines.append(f"  {snippet[:240]}" + ("…" if len(snippet) > 240 else ""))
        note = str(data.get("note") or "")
        if note:
            lines.append(note)
        return "\n".join(lines)


# 2. Git Formatters
class GitPRListFormatter(FormatterStrategy):
    def render(self, data: dict[str, Any], *, slack: bool = False) -> str:
        # data might contain raw prs or list of PullRequestSummary dicts
        raw_prs = data.get("prs") or []
        prs: list[PullRequestSummary] = []
        for item in raw_prs:
            if isinstance(item, PullRequestSummary):
                prs.append(item)
            elif isinstance(item, dict):
                from backend.tools.result import pr_summary_from_dict
                prs.append(pr_summary_from_dict(item))

        state = str(data.get("state") or "open")
        if not prs:
            state_label = state if state != "all" else ""
            prefix = f"{state_label} " if state_label else ""
            return f"No {prefix.strip()} pull requests found.".strip()

        count = len(prs)
        state_word = state if state in ("open", "closed") else "matching"
        header_text = f"{count} {state_word} PR{'s' if count != 1 else ''}"
        header = f"*{header_text}*" if slack else f"**{header_text}**"

        by_repo: dict[str, list[PullRequestSummary]] = defaultdict(list)
        for pr in prs:
            short = pr.repo.rsplit("/", 1)[-1] if pr.repo else "unknown"
            by_repo[short].append(pr)

        lines = [header]
        if not slack:
            lines.append("")
        for repo_short in sorted(by_repo.keys()):
            if slack:
                lines.append(f"\n`{repo_short}`")
            else:
                lines.append(f"### {repo_short}")
            for pr in sorted(by_repo[repo_short], key=lambda item: item.number, reverse=True):
                draft = " _(draft)_" if pr.draft else ""
                label = f"#{pr.number} {pr.title}"
                if slack and pr.url:
                    bullet = f"• <{pr.url}|{label}>{draft}"
                elif pr.url:
                    bullet = f"- [{label}]({pr.url}){draft}"
                else:
                    bullet = f"- {label}{draft}"
                lines.append(bullet)
            if not slack:
                lines.append("")

        return "\n".join(lines).strip()


class GitPRDetailFormatter(FormatterStrategy):
    def render(self, data: dict[str, Any], *, slack: bool = False) -> str:
        pr_data = data.get("pr") or data
        number = pr_data.get("number")
        title = pr_data.get("title") or "Untitled"
        repo = pr_data.get("repo") or ""
        repo_short = repo.rsplit("/", 1)[-1] if repo else ""
        url = str(pr_data.get("url") or "")
        state = str(pr_data.get("state") or "")
        author = str(pr_data.get("author") or "")
        head = pr_data.get("head")
        base = pr_data.get("base")
        draft = pr_data.get("draft")

        if slack and url:
            title_line = f"<{url}|#{number} {title}>"
        elif url:
            title_line = f"[#{number} {title}]({url})"
        else:
            title_line = f"#{number} {title}"

        header = f"*PR in `{repo_short}`*" if slack else f"**PR in `{repo_short}`**"
        lines = [header, title_line]
        meta = []
        if state:
            meta.append(state)
        if author:
            meta.append(f"by `{author}`")
        if draft:
            meta.append("draft")
        if meta:
            lines.append(" · ".join(meta))
        if head and base:
            lines.append(f"`{head}` → `{base}`")

        body = (pr_data.get("body") or "").strip()
        if body:
            snippet = body if len(body) <= 400 else body[:397] + "..."
            lines.append(f"\n{snippet}")

        return "\n".join(lines).strip()


class GitPRCreatedFormatter(FormatterStrategy):
    def render(self, data: dict[str, Any], *, slack: bool = False) -> str:
        pr_data = data.get("pr") or data
        detail_formatter = GitPRDetailFormatter()
        header = "*Draft PR opened*" if slack else "**Draft PR opened**"
        body = detail_formatter.render({"pr": pr_data}, slack=slack)
        return f"{header}\n{body}"


# 3. Jira Formatters
class JiraListFormatter(FormatterStrategy):
    def render(self, data: dict[str, Any], *, slack: bool = False) -> str:
        raw_issues = data.get("issues") or []
        issues: list[JiraIssueSummary] = []
        for item in raw_issues:
            if isinstance(item, JiraIssueSummary):
                issues.append(item)
            elif isinstance(item, dict):
                from backend.tools.result import jira_summary_from_dict
                issues.append(jira_summary_from_dict(item))

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


class JiraDetailFormatter(FormatterStrategy):
    def render(self, data: dict[str, Any], *, slack: bool = False) -> str:
        detail = data.get("issue") or data
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


class JiraActionFormatter(FormatterStrategy):
    def render(self, data: dict[str, Any], *, slack: bool = False) -> str:
        action = str(data.get("action") or "")
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


# Map kinds to strategy classes
KIND_FORMATTERS: dict[str, FormatterStrategy] = {
    "athena_query": AthenaQueryFormatter(),
    "cloudwatch_query": CloudWatchQueryFormatter(),
    "cloudwatch_log_groups": CloudWatchLogGroupsFormatter(),
    "web_search": WebSearchFormatter(),
    "pr_list": GitPRListFormatter(),
    "pr_detail": GitPRDetailFormatter(),
    "pr_created": GitPRCreatedFormatter(),
    "jira_list": JiraListFormatter(),
    "jira_detail": JiraDetailFormatter(),
    "jira_action": JiraActionFormatter(),
}


# 4. Channel Decorators

def _process_outside_fences(text: str, transform: Callable[[str], str]) -> str:
    lines = text.split("\n")
    output: list[str] = []
    in_fence = False
    chunk: list[str] = []

    def flush_chunk() -> None:
        nonlocal chunk
        if chunk:
            output.append(transform("\n".join(chunk)))
            chunk = []

    for line in lines:
        if _FENCE_RE.match(line.strip()):
            flush_chunk()
            in_fence = not in_fence
            output.append(line)
            continue
        if in_fence:
            output.append(line)
        else:
            chunk.append(line)

    flush_chunk()
    return "\n".join(output)


def format_for_slack(text: str) -> str:
    """Normalize model output for Slack mrkdwn."""

    def apply(t: str) -> str:
        t = _DOUBLE_BOLD_RE.sub(r"*\1*", t)
        t = _MD_HEADING_RE.sub(r"*\1*", t)
        t = _normalize_table_titles(t)
        t = _convert_markdown_tables(t)
        t = _merge_backtick_pipe_rows(t)
        t = _strip_remaining_pipe_lines(t)
        t = _normalize_fenced_pipe_tables(t)
        t = _linkify_github_pr_urls(t)
        t = _collapse_extra_blank_lines(t)
        return t

    text = _process_outside_fences(text, apply)
    text = _sanitize_fenced_blocks(text)
    return text.strip()


def format_for_github(text: str) -> str:
    """Convert Slack-oriented table fences to GFM tables; light UI cleanup."""
    text = _fenced_pipe_tables_to_gfm(text)
    text = _backtick_pipe_rows_to_gfm(text)
    return format_for_ui(text).strip()


def format_for_ui(text: str) -> str:
    """Convert Slack-style mrkdwn leftovers into clean Markdown for the UI."""

    def apply(t: str) -> str:
        t = _SLACK_LINK_RE.sub(r"[\2](\1)", t)
        t = _SLACK_BOLD_RE.sub(r"**\1**", t)

        lines: list[str] = []
        for line in t.split("\n"):
            for normalized in _normalize_ui_line(line):
                lines.append(normalized)
        return "\n".join(lines)

    return _process_outside_fences(text, apply).strip()


# Supporting Slack/UI formatting functions
def _normalize_table_titles(text: str) -> str:
    lines = []
    for line in text.split("\n"):
        if _TABLE_TITLE_RE.match(line.strip()):
            period = "yesterday" if "yesterday" in line.lower() else "period"
            lines.append(f"*Alert summary ({period})*")
        else:
            lines.append(line)
    return "\n".join(lines)


def _convert_markdown_tables(text: str) -> str:
    lines = text.split("\n")
    output: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if _is_table_row(line):
            table_lines: list[str] = []
            while index < len(lines) and _is_table_row(lines[index]):
                table_lines.append(lines[index])
                index += 1
            converted = _table_to_code_block(table_lines)
            if converted:
                output.append(converted)
            continue
        output.append(line)
        index += 1
    return "\n".join(output)


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _TABLE_ROW_RE.match(stripped):
        return True
    return stripped.count("|") >= 2 and not stripped.startswith("http")


def _merge_backtick_pipe_rows(text: str) -> str:
    lines = text.split("\n")
    output: list[str] = []
    index = 0
    while index < len(lines):
        match = _BACKTICK_PIPE_RE.match(lines[index].strip())
        if not match:
            output.append(lines[index])
            index += 1
            continue
        block_lines: list[str] = []
        while index < len(lines):
            row_match = _BACKTICK_PIPE_RE.match(lines[index].strip())
            if not row_match:
                break
            block_lines.append(row_match.group(1))
            index += 1
        converted = _pipe_rows_to_code_block(block_lines)
        if converted:
            output.append(converted)
        else:
            output.extend(f"`{row}`" for row in block_lines)
    return "\n".join(output)


def _pipe_rows_to_code_block(rows: list[str]) -> str:
    parsed = [[cell.strip() for cell in row.split("|")] for row in rows if row.strip()]
    if len(parsed) < 2:
        return ""
    headers = parsed[0]
    data = parsed[1:]
    if _looks_like_header(headers) and data:
        return format_code_table(headers, data)
    if data:
        generic_headers = [f"Col {index + 1}" for index in range(len(parsed[0]))]
        return format_code_table(generic_headers, parsed)
    return ""


def _normalize_fenced_pipe_tables(text: str) -> str:
    lines = text.split("\n")
    output: list[str] = []
    index = 0
    while index < len(lines):
        if lines[index].strip() != "```":
            output.append(lines[index])
            index += 1
            continue
        start = index
        index += 1
        block: list[str] = []
        while index < len(lines) and lines[index].strip() != "```":
            block.append(lines[index])
            index += 1
        end = index if index < len(lines) else start
        if block and any(" | " in line for line in block) and not _block_is_csv(block):
            rows = []
            for line in block:
                if set(line.replace("|", "").replace(" ", "")) <= {"-"}:
                    continue
                if " | " in line:
                    rows.append([cell.strip() for cell in line.split("|")])
            if len(rows) >= 2:
                output.append(format_code_table(rows[0], rows[1:]))
            else:
                output.extend(lines[start : end + 1])
        else:
            output.extend(lines[start : end + 1])
        index = end + 1
    return "\n".join(output)


def _sanitize_fenced_blocks(text: str) -> str:
    lines = text.split("\n")
    output: list[str] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped.startswith("```"):
            output.append(lines[index])
            index += 1
            continue
        index += 1
        block: list[str] = []
        while index < len(lines) and not lines[index].strip().startswith("```"):
            block.append(lines[index])
            index += 1
        converted = _convert_fenced_block(block)
        if converted:
            output.append(converted)
        else:
            output.append("```")
            output.extend(block)
            output.append("```")
        if index < len(lines):
            index += 1
    return "\n".join(output)


def _convert_fenced_block(block: list[str]) -> str | None:
    if not block:
        return None
    cleaned: list[str] = []
    for line in block:
        stripped = line.strip()
        match = _BACKTICK_PIPE_RE.match(stripped)
        if match:
            cleaned.append(match.group(1))
            continue
        if stripped.startswith("`") and stripped.endswith("`") and "|" in stripped:
            cleaned.append(stripped.strip("`"))
            continue
        cleaned.append(line)

    if not any("|" in line for line in cleaned):
        return None
    if _block_is_csv(cleaned):
        return None

    rows = [[cell.strip() for cell in line.split("|")] for line in cleaned if "|" in line and not _is_dash_separator(line)]
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    if len(rows) < 2:
        return None
    return format_code_table(rows[0], rows[1:])


def _is_dash_separator(line: str) -> bool:
    compact = line.replace("|", "").replace("-", "").replace(":", "").replace(" ", "")
    return not compact and "-" in line


def _block_is_csv(block: list[str]) -> bool:
    sample = block[0] if block else ""
    return sample.count(",") >= 2 and " | " not in sample


def _strip_remaining_pipe_lines(text: str) -> str:
    output: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if _is_table_row(stripped) and not _TABLE_SEP_RE.match(stripped):
            bullet = _pipe_line_to_code_row(stripped)
            output.append(bullet or line)
        else:
            output.append(line)
    return "\n".join(output)


def _pipe_line_to_code_row(line: str) -> str | None:
    cells = _split_cells(line)
    if len(cells) < 2 or _looks_like_header(cells):
        return None
    return f"`{' | '.join(cells)}`"


def _split_cells(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|") if cell.strip()]


def _looks_like_header(cells: list[str]) -> bool:
    joined = " ".join(cells).lower()
    header_words = (
        "category",
        "count",
        "merchant",
        "error",
        "file path",
        "impact risk",
        "compatibility",
        "downstream",
        "breaking",
    )
    return joined in {"category count", "category | count"} or cells == ["Category", "Count"] or any(
        word in joined for word in header_words
    )


def _table_to_code_block(table_lines: list[str]) -> str:
    rows: list[list[str]] = []
    for line in table_lines:
        if _TABLE_SEP_RE.match(line.strip()) or _is_dash_separator(line.strip()):
            continue
        cells = _split_cells(line)
        if cells:
            rows.append(cells)
    if len(rows) < 2:
        if len(rows) == 1:
            if len(rows[0]) == 2:
                return format_code_table(["Item", "Value"], [rows[0]])
            return format_code_table(["Details"], [[" — ".join(rows[0])]])
        return ""

    headers = rows[0]
    data = rows[1:]
    return format_code_table(headers, data)


def format_code_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def fmt(cells: list[str]) -> str:
        return " | ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(cells))

    body = [fmt(headers), fmt(["-" * width for width in widths])]
    body.extend(fmt(row) for row in rows)
    return "```\n" + "\n".join(body) + "\n```"


def _linkify_github_pr_urls(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        prefix = match.group(1)
        url = match.group(2).strip()
        number = match.group(3)
        if "<" in prefix and "|" in text[match.start() : match.end() + 5]:
            return match.group(0)
        return f"{prefix.rstrip()}<{url}|#{number}>"

    return _GITHUB_PR_URL_RE.sub(repl, text)


def _collapse_extra_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# GFM Table converter for Github Format
def _fenced_pipe_tables_to_gfm(text: str) -> str:
    lines = text.split("\n")
    output: list[str] = []
    index = 0
    while index < len(lines):
        if lines[index].strip() != "```":
            output.append(lines[index])
            index += 1
            continue
        start = index
        index += 1
        block: list[str] = []
        while index < len(lines) and lines[index].strip() != "```":
            block.append(lines[index])
            index += 1
        end = index if index < len(lines) else start
        converted = _block_to_gfm_table(block)
        if converted:
            output.append(converted)
        else:
            output.extend(lines[start : end + 1])
        index = end + 1
    return "\n".join(output)


def _backtick_pipe_rows_to_gfm(text: str) -> str:
    lines = text.split("\n")
    output: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not (
            stripped.startswith("`")
            and "|" in stripped
            and (stripped.endswith("`") or stripped.endswith("`|"))
        ):
            output.append(line)
            index += 1
            continue
        block: list[str] = []
        while index < len(lines):
            row = lines[index].strip()
            if row.startswith("`") and "|" in row:
                block.append(lines[index])
                index += 1
                continue
            break
        converted = _block_to_gfm_table(block)
        if converted:
            output.append(converted)
        else:
            output.extend(block)
    return "\n".join(output)


def _block_to_gfm_table(block: list[str]) -> str | None:
    if not block:
        return None
    rows: list[list[str]] = []
    for line in block:
        parsed = _parse_table_row(line)
        if parsed is None:
            continue
        if _is_dash_separator_gfm("|".join(parsed)):
            continue
        if parsed and all(set(cell) <= {"-"} for cell in parsed):
            continue
        rows.append(parsed)
    if len(rows) < 2:
        return None
    if not any(" | " in line or "|" in line for line in block):
        return None
    return _gfm_table(rows[0], rows[1:])


def _parse_table_row(line: str) -> list[str] | None:
    stripped = line.strip()
    match = _BACKTICK_PIPE_RE.match(stripped)
    if match:
        stripped = match.group(1)
    elif stripped.startswith("`") and stripped.endswith("`"):
        stripped = stripped.strip("`")
    if "|" not in stripped:
        return None
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    if not any(cells):
        return None
    return cells


def _is_dash_separator_gfm(line: str) -> bool:
    compact = line.replace("|", "").replace("-", "").replace(":", "").replace(" ", "")
    return not compact and "-" in line


def _gfm_table(headers: list[str], rows: list[list[str]]) -> str:
    width = len(headers)

    def esc(cell: str) -> str:
        return cell.replace("|", "\\|").strip()

    header_line = "| " + " | ".join(esc(h) for h in headers) + " |"
    sep_line = "| " + " | ".join("---" for _ in headers) + " |"
    body_lines: list[str] = []
    for row in rows:
        padded = row + [""] * max(0, width - len(row))
        body_lines.append("| " + " | ".join(esc(c) for c in padded[:width]) + " |")
    return "\n".join([header_line, sep_line, *body_lines])


def _normalize_ui_line(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped:
        return [""]

    if match := _REPO_LINE_RE.match(stripped):
        return ["", f"### {match.group(1)}"]

    if "•" in stripped:
        parts = [part.strip() for part in re.split(r"\s*•\s*", stripped) if part.strip()]
        if len(parts) > 1:
            out: list[str] = []
            for part in parts:
                out.extend(_normalize_ui_line(part))
            return out

    if match := _PR_BULLET_RE.match(stripped):
        label = match.group(1).strip()
        url = match.group(2)
        if url:
            return [f"- [{label}]({url})"]
        return [f"- {label}"]

    if match := _PR_PLAIN_RE.match(stripped):
        return [f"- [{match.group(1).strip()}]({match.group(2)})"]

    return [line]


# 5. Backward-Compatible Functional Wrappers

def format_prs(prs: list[PullRequestSummary], *, slack: bool = True, state: str = "open") -> str:
    return GitPRListFormatter().render({"prs": prs, "state": state}, slack=slack)


def format_pr_detail(data: dict[str, Any], *, slack: bool = True) -> str:
    return GitPRDetailFormatter().render(data, slack=slack)


def format_jira_issues(issues: list[JiraIssueSummary], *, slack: bool = False) -> str:
    return JiraListFormatter().render({"issues": issues}, slack=slack)


def format_jira_detail(detail: dict, *, slack: bool = False) -> str:
    return JiraDetailFormatter().render(detail, slack=slack)


def format_jira_action(action: str, data: dict, *, slack: bool = False) -> str:
    return JiraActionFormatter().render({**data, "action": action}, slack=slack)

