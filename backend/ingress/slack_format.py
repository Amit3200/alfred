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


def format_for_slack(text: str) -> str:
    text = _process_outside_fences(text, _apply_slack_formatting)
    return text.strip()


def _apply_slack_formatting(text: str) -> str:
    text = _DOUBLE_BOLD_RE.sub(r"*\1*", text)
    text = _MD_HEADING_RE.sub(r"*\1*", text)
    text = _normalize_table_titles(text)
    text = _convert_markdown_tables(text)
    text = _strip_remaining_pipe_lines(text)
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
    return joined in {"category count", "category | count"} or cells == ["Category", "Count"]


def _table_to_code_block(table_lines: list[str]) -> str:
    rows: list[list[str]] = []
    for line in table_lines:
        if _TABLE_SEP_RE.match(line.strip()):
            continue
        cells = _split_cells(line)
        if cells and not _looks_like_header(cells):
            rows.append(cells)
    if not rows:
        return ""

    if len(rows) == 1:
        if len(rows[0]) == 2:
            return format_code_table(["Item", "Value"], [rows[0]])
        return format_code_table(["Details"], [[" — ".join(rows[0])]])

    headers = rows[0]
    data = rows[1:]
    if not data:
        return format_code_table(["Details"], [headers])
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
