"""Format assistant output for GitHub issue/PR comments (GFM)."""

from __future__ import annotations

import re

from backend.ingress.ui_format import format_for_ui

_BACKTICK_PIPE_RE = re.compile(r"^`(.+)`$")
_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")


def format_for_github(text: str) -> str:
    """Convert Slack-oriented table fences to GFM tables; light UI cleanup."""
    text = _fenced_pipe_tables_to_gfm(text)
    text = _backtick_pipe_rows_to_gfm(text)
    return format_for_ui(text).strip()


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
        if _is_dash_separator("|".join(parsed)):
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


def _is_dash_separator(line: str) -> bool:
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
