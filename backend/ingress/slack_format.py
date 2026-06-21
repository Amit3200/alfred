"""Normalize model output for Slack mrkdwn."""

from __future__ import annotations

import re
from typing import Callable

_DOUBLE_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_MD_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
_TABLE_ROW_RE = re.compile(r"^\s*\|(.+?)\|?\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|[\s:\-|]+\|?\s*$")
_TABLE_TITLE_RE = re.compile(r"^alert summary table\b", re.I)
_FENCE_RE = re.compile(r"^```")
_BACKTICK_PIPE_RE = re.compile(r"^`([^`|]+(?:\s*\|\s*[^`|]+)+)`$")


def format_for_slack(text: str) -> str:
    text = _process_outside_fences(text, _apply_slack_formatting)
    text = _sanitize_fenced_blocks(text)
    return text.strip()


def _apply_slack_formatting(text: str) -> str:
    text = _DOUBLE_BOLD_RE.sub(r"*\1*", text)
    text = _MD_HEADING_RE.sub(r"*\1*", text)
    text = _normalize_table_titles(text)
    text = _convert_markdown_tables(text)
    text = _merge_backtick_pipe_rows(text)
    text = _strip_remaining_pipe_lines(text)
    text = _normalize_fenced_pipe_tables(text)
    text = _linkify_github_pr_urls(text)
    text = _collapse_extra_blank_lines(text)
    return text


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
    """Normalize pipe tables that models wrap in ``` blocks with per-row backticks."""
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
    """Render a monospace table inside a Slack-friendly fenced code block."""
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def fmt(cells: list[str]) -> str:
        return " | ".join(cell.ljust(widths[index]) for index, cell in enumerate(cells))

    body = [fmt(headers), fmt(["-" * width for width in widths])]
    body.extend(fmt(row) for row in rows)
    return "```\n" + "\n".join(body) + "\n```"


_GITHUB_PR_URL_RE = re.compile(
    r"^(\s*(?:[-*•]\s*)?)(https://github\.com/[^/\s]+/[^/\s]+/pull/(\d+)(?:\s|$))",
    re.MULTILINE,
)


def _linkify_github_pr_urls(text: str) -> str:
    """Turn bare GitHub PR URLs into Slack mrkdwn links when not already linked."""

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
