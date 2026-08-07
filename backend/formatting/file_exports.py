"""Detect export requests and build Slack file attachments from tabular replies."""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from typing import Literal

from backend.formatting.strategies import format_code_table

ExportFormat = Literal["csv", "tsv", "json"]

_FENCE_RE = re.compile(r"^```(?:csv|tsv|json)?\s*$", re.IGNORECASE)
_BACKTICK_PIPE_RE = re.compile(r"^`([^`]+)`$")
_TABLE_ROW_RE = re.compile(r"^\s*\|(.+?)\|?\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|[\s:\-|]+\|?\s*$")

_EXPORT_MARKERS: dict[ExportFormat, tuple[str, ...]] = {
    "csv": ("csv", "comma-separated", "comma separated"),
    "tsv": ("tsv", "tab-separated", "tab separated"),
    "json": ("json", "json file"),
}


@dataclass
class SlackFileAttachment:
    filename: str
    content: bytes
    mime_type: str
    title: str = ""


@dataclass
class SlackDelivery:
    text: str
    files: list[SlackFileAttachment] = field(default_factory=list)
    blocks: list[dict] | None = None


@dataclass
class TabularData:
    headers: list[str]
    rows: list[list[str]]


def prepare_slack_delivery(rendered_text: str, intent: str) -> SlackDelivery:
    """Format reply text and optionally attach export files or handle length truncation."""
    export_format = detect_export_format(intent)
    if export_format:
        table = extract_tabular_data(rendered_text)
        if table is not None and table.rows:
            attachment = build_export_attachment(table, export_format)
            preview = format_code_table(table.headers, table.rows[:5])
            row_label = "row" if len(table.rows) == 1 else "rows"
            intro = (
                f"*Attached:* `{attachment.filename}` ({len(table.rows)} {row_label})\n\n"
                f"*Preview:*\n{preview}"
            )
            if len(table.rows) > 5:
                intro += f"\n\n_…and {len(table.rows) - 5} more in the file._"
            return SlackDelivery(text=intro, files=[attachment])

    # If the text is very long (exceeds 3,500 characters), attach it as a file snippet!
    if len(rendered_text) > 3500:
        filename = "alfred-reply.md"
        # Use a more descriptive name if it looks like a PR review
        if "review" in intent.lower() or "pr" in intent.lower():
            filename = "pr-review-report.md"
            
        attachment = SlackFileAttachment(
            filename=filename,
            content=rendered_text.encode("utf-8"),
            mime_type="text/markdown",
            title="Alfred Report",
        )
        
        # Take a short prefix of the text to show as an intro in the thread
        lines = rendered_text.splitlines()
        prefix_lines = []
        char_count = 0
        for line in lines:
            if char_count + len(line) > 800:
                break
            prefix_lines.append(line)
            char_count += len(line) + 1
            
        intro = (
            f"⚠️ *Alfred Response:* This report exceeds Slack's character limit, so the full version has been attached as a file below.\n\n"
            f"--- *Preview* ---\n"
            + "\n".join(prefix_lines)
            + "\n\n... (full report attached below) ..."
        )
        return SlackDelivery(text=intro, files=[attachment])

    return SlackDelivery(text=rendered_text)


def detect_export_format(intent: str) -> ExportFormat | None:
    lower = intent.lower()
    for fmt, markers in _EXPORT_MARKERS.items():
        if any(marker in lower for marker in markers):
            return fmt
    if any(marker in lower for marker in ("export", "download", "attach", "spreadsheet")):
        return "csv"
    return None


def extract_tabular_data(text: str) -> TabularData | None:
    for parser in (
        _parse_csv_fence,
        _parse_pipe_table,
        _parse_pipe_code_block,
        _parse_backtick_pipe_rows,
    ):
        parsed = parser(text)
        if parsed is not None:
            return parsed
    return None


def build_export_attachment(table: TabularData, export_format: ExportFormat) -> SlackFileAttachment:
    if export_format == "json":
        payload = [dict(zip(table.headers, row, strict=False)) for row in table.rows]
        content = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        return SlackFileAttachment(
            filename="alfred-export.json",
            content=content,
            mime_type="application/json",
            title="Alfred export",
        )
    delimiter = "\t" if export_format == "tsv" else ","
    extension = "tsv" if export_format == "tsv" else "csv"
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\n")
    writer.writerow(table.headers)
    writer.writerows(table.rows)
    return SlackFileAttachment(
        filename=f"alfred-export.{extension}",
        content=buffer.getvalue().encode("utf-8"),
        mime_type="text/tab-separated-values" if export_format == "tsv" else "text/csv",
        title="Alfred export",
    )


def _parse_csv_fence(text: str) -> TabularData | None:
    for block in _fenced_blocks(text):
        stripped = block.strip()
        if not stripped or "\n" not in stripped:
            continue
        lines = [line for line in stripped.splitlines() if line.strip()]
        if not lines:
            continue
        delimiter = _guess_delimiter(lines[0])
        if delimiter is None:
            continue
        reader = csv.reader(lines, delimiter=delimiter)
        rows = [row for row in reader if any(cell.strip() for cell in row)]
        if len(rows) < 2:
            continue
        headers = [cell.strip() for cell in rows[0]]
        data = [[cell.strip() for cell in row] for row in rows[1:] if row]
        if headers and data:
            return TabularData(headers=headers, rows=_normalize_rows(headers, data))
    return None


def _parse_pipe_table(text: str) -> TabularData | None:
    lines = text.splitlines()
    table_lines: list[str] = []
    for line in lines:
        if _TABLE_ROW_RE.match(line.strip()) and not line.strip().startswith("```"):
            table_lines.append(line)
        elif table_lines:
            break
    if len(table_lines) < 2:
        return None
    rows: list[list[str]] = []
    for line in table_lines:
        if _TABLE_SEP_RE.match(line.strip()):
            continue
        cells = _split_cells(line)
        if cells:
            rows.append(cells)
    if len(rows) < 2:
        return None
    headers = rows[0]
    data = rows[1:]
    return TabularData(headers=headers, rows=_normalize_rows(headers, data))


def _parse_pipe_code_block(text: str) -> TabularData | None:
    for block in _fenced_blocks(text):
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        if not any(" | " in line for line in lines):
            continue
        rows: list[list[str]] = []
        for line in lines:
            if set(line.replace("|", "").replace(" ", "")) <= {"-"}:
                continue
            if " | " in line:
                rows.append([cell.strip() for cell in line.split("|")])
        if len(rows) >= 2:
            headers = rows[0]
            data = rows[1:]
            return TabularData(headers=headers, rows=_normalize_rows(headers, data))
    return None


def _parse_backtick_pipe_rows(text: str) -> TabularData | None:
    rows: list[list[str]] = []
    headers: list[str] | None = None
    for line in text.splitlines():
        match = _BACKTICK_PIPE_RE.match(line.strip())
        if not match or " | " not in match.group(1):
            if rows and headers:
                break
            continue
        cells = [cell.strip() for cell in match.group(1).split("|")]
        if not cells:
            continue
        if headers is None and _looks_like_header(cells):
            headers = cells
            continue
        if headers is None:
            headers = [f"Column {index + 1}" for index in range(len(cells))]
        rows.append(cells)
    if headers and rows:
        return TabularData(headers=headers, rows=_normalize_rows(headers, rows))
    return None


def _fenced_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        if _FENCE_RE.match(lines[index].strip()):
            index += 1
            chunk: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                chunk.append(lines[index])
                index += 1
            blocks.append("\n".join(chunk))
        index += 1
    return blocks


def _guess_delimiter(header_line: str) -> str | None:
    if header_line.count(",") >= 1:
        return ","
    if header_line.count("\t") >= 1:
        return "\t"
    if header_line.count("|") >= 2:
        return "|"
    return None


def _split_cells(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|") if cell.strip()]


def _looks_like_header(cells: list[str]) -> bool:
    joined = " ".join(cells).lower()
    header_words = ("merchant", "count", "category", "error", "type", "status", "severity", "date")
    return any(word in joined for word in header_words)


def _normalize_rows(headers: list[str], rows: list[list[str]]) -> list[list[str]]:
    width = len(headers)
    normalized: list[list[str]] = []
    for row in rows:
        padded = row[:width] + [""] * max(0, width - len(row))
        normalized.append(padded[:width])
    return normalized
