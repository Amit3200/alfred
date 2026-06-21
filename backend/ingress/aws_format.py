"""Format AWS tool results for Slack and UI."""

from __future__ import annotations

from typing import Any


def format_athena_query(data: dict[str, Any], *, slack: bool = False) -> str:
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


def format_cloudwatch_query(data: dict[str, Any], *, slack: bool = False) -> str:
    log_group = str(data.get("log_group") or "")
    rows = data.get("rows") or []
    row_count = int(data.get("row_count") or len(rows))
    start = str(data.get("start_time") or "")
    end = str(data.get("end_time") or "")

    header = (
        f"*CloudWatch Logs* `{log_group}` — {row_count} row(s)"
        if slack
        else f"CloudWatch Logs `{log_group}` — {row_count} row(s)"
    )
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


def format_cloudwatch_log_groups(groups: list[str], *, prefix: str = "", slack: bool = False) -> str:
    if not groups:
        target = prefix or "search"
        return f"No CloudWatch log groups matched `{target}`."
    bullet = "•" if slack else "-"
    title = f"*{len(groups)} log group(s)*" if slack else f"{len(groups)} log group(s):"
    lines = [title]
    for group in groups:
        lines.append(f"{bullet} `{group}`")
    return "\n".join(lines)


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
    if slack:
        return f"```\n{table}\n```"
    return f"```\n{table}\n```"


def format_grade_events_query(data: dict[str, Any], *, slack: bool = False) -> str:
    guardrails = data.get("guardrails") or {}
    table = str(data.get("table") or guardrails.get("table") or "grade_events")
    rows = data.get("rows") or []
    columns = [str(col) for col in data.get("columns") or []]
    row_count = int(data.get("row_count") or len(rows))

    header = (
        f"*grade_events* `{table}` — {row_count} row(s)"
        if slack
        else f"grade_events `{table}` — {row_count} row(s)"
    )
    meta_parts: list[str] = []
    if guardrails.get("time_window"):
        meta_parts.append(str(guardrails["time_window"]).replace("_", " "))
    if guardrails.get("limit") is not None:
        meta_parts.append(f"limit {guardrails['limit']}")
    if guardrails.get("full_data"):
        meta_parts.append("full data")

    lines = [header]
    if meta_parts:
        lines.append(" · ".join(meta_parts))
    if not rows:
        lines.append("No matching grade_events rows.")
        return "\n".join(lines)

    if columns:
        lines.append("")
        lines.append(_format_table(columns, rows, slack=slack, max_rows=20))
    return "\n".join(lines)
