"""Persist recent routing traces for admin debugging."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

_MAX_TRACES = 200
_LOCK = Lock()


@dataclass
class RoutingTraceRecord:
    task_id: str
    recorded_at: str
    intent: str
    skill_name: str = ""
    routing_strategy: str = ""
    tool_plan: dict[str, Any] | None = None
    scoped_tools: list[str] = field(default_factory=list)
    graph_route: str = ""
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    grounding_passed: bool = True
    grounding_issues: list[str] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    source: str = ""
    channel_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _trace_path(data_dir: Path) -> Path:
    return data_dir / "routing_traces.json"


def _load_all(data_dir: Path) -> list[dict[str, Any]]:
    path = _trace_path(data_dir)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _save_all(data_dir: Path, records: list[dict[str, Any]]) -> None:
    path = _trace_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records[-_MAX_TRACES:], indent=2), encoding="utf-8")


def record_trace(data_dir: Path, record: RoutingTraceRecord) -> None:
    with _LOCK:
        records = _load_all(data_dir)
        payload = record.to_dict()
        records = [r for r in records if r.get("task_id") != record.task_id]
        records.append(payload)
        try:
            _save_all(data_dir, records)
        except OSError as exc:
            logger.warning("Failed to save routing trace: %s", exc)


def build_trace_record(
    *,
    task_id: str,
    intent: str,
    skill_name: str = "",
    routing_strategy: str = "",
    tool_plan: dict[str, Any] | None = None,
    scoped_tools: list[str] | None = None,
    graph_route: str = "",
    tool_trace: list[dict[str, Any]] | None = None,
    grounding_passed: bool = True,
    grounding_issues: list[str] | None = None,
    steps: list[dict[str, Any]] | None = None,
    source: str = "",
    channel_id: str = "",
) -> RoutingTraceRecord:
    return RoutingTraceRecord(
        task_id=task_id,
        recorded_at=datetime.now(timezone.utc).isoformat(),
        intent=intent,
        skill_name=skill_name,
        routing_strategy=routing_strategy,
        tool_plan=tool_plan,
        scoped_tools=list(scoped_tools or []),
        graph_route=graph_route,
        tool_trace=list(tool_trace or []),
        grounding_passed=grounding_passed,
        grounding_issues=list(grounding_issues or []),
        steps=list(steps or []),
        source=source,
        channel_id=channel_id,
    )


def list_traces(data_dir: Path, *, limit: int = 50) -> list[dict[str, Any]]:
    records = _load_all(data_dir)
    records.sort(key=lambda r: r.get("recorded_at") or "", reverse=True)
    return records[: max(1, min(limit, _MAX_TRACES))]


def get_trace(data_dir: Path, task_id: str) -> dict[str, Any] | None:
    target = task_id.strip()
    for record in reversed(_load_all(data_dir)):
        if record.get("task_id") == target:
            return record
    return None
