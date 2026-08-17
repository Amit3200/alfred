"""Observability API — usage summaries, timeseries, and event logs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query

from backend.api.deps import get_manager, require_admin
from backend.config_manager import ConfigManager
from backend.observability.models import ObservabilityFilters, TimeseriesBucket
from backend.observability.pricing import build_pricing_table
from backend.observability.store import SQLiteObservabilityStore
from backend.observability.users import UserLabelEnricher
from pydantic import BaseModel

router = APIRouter(prefix="/observability", tags=["observability"])


class ToggleScheduleRequest(BaseModel):
    active: bool


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _default_since(preset: str | None) -> datetime:
    now = datetime.now(timezone.utc)
    if preset == "24h":
        return now - timedelta(hours=24)
    if preset == "7d":
        return now - timedelta(days=7)
    if preset == "30d":
        return now - timedelta(days=30)
    if preset == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return now - timedelta(days=7)


def _filters_from_query(
    *,
    since: str | None,
    until: str | None,
    preset: str | None,
    source: str | None,
    user: str | None,
    model: str | None,
    provider: str | None,
    event_type: Literal["llm_call", "tool_call"] | None,
    tool_category: str | None,
) -> ObservabilityFilters:
    parsed_since = _parse_dt(since) or _default_since(preset)
    parsed_until = _parse_dt(until) or datetime.now(timezone.utc)
    return ObservabilityFilters(
        since=parsed_since,
        until=parsed_until,
        source=source or None,
        user_label=user or None,
        model=model or None,
        provider=provider or None,
        event_type=event_type,
        tool_category=tool_category or None,
    )


def _store(manager: ConfigManager) -> SQLiteObservabilityStore:
    return SQLiteObservabilityStore(manager.data_dir)


def _enricher(manager: ConfigManager) -> UserLabelEnricher:
    config, _ = manager.load_merged()
    return UserLabelEnricher.from_config(config, data_dir=manager.data_dir)


def _pricing_table(manager: ConfigManager):
    config, _ = manager.load_merged()
    return build_pricing_table(config.observability)


@router.get("/summary")
def usage_summary(
    manager: ConfigManager = Depends(require_admin),
    since: str | None = Query(None),
    until: str | None = Query(None),
    preset: str | None = Query("7d"),
    source: str | None = Query(None),
    user: str | None = Query(None),
    model: str | None = Query(None),
    provider: str | None = Query(None),
    event_type: Literal["llm_call", "tool_call"] | None = Query(None),
    tool_category: str | None = Query(None),
) -> dict[str, Any]:
    filters = _filters_from_query(
        since=since,
        until=until,
        preset=preset,
        source=source,
        user=user,
        model=model,
        provider=provider,
        event_type=event_type,
        tool_category=tool_category,
    )
    store = _store(manager)
    enricher = _enricher(manager)
    summary = store.summary(filters, pricing=_pricing_table(manager))
    summary.by_user = enricher.merge_by_user(summary.by_user, store.user_breakdown(filters))
    return {
        "filters": filters.model_dump(mode="json"),
        "summary": summary.model_dump(),
    }


@router.get("/timeseries")
def usage_timeseries(
    manager: ConfigManager = Depends(require_admin),
    bucket: TimeseriesBucket = Query("day"),
    since: str | None = Query(None),
    until: str | None = Query(None),
    preset: str | None = Query("7d"),
    source: str | None = Query(None),
    user: str | None = Query(None),
    model: str | None = Query(None),
    provider: str | None = Query(None),
    event_type: Literal["llm_call", "tool_call"] | None = Query(None),
    tool_category: str | None = Query(None),
) -> dict[str, Any]:
    filters = _filters_from_query(
        since=since,
        until=until,
        preset=preset,
        source=source,
        user=user,
        model=model,
        provider=provider,
        event_type=event_type,
        tool_category=tool_category,
    )
    series = _store(manager).timeseries(filters, bucket=bucket, pricing=_pricing_table(manager))
    return {
        "filters": filters.model_dump(mode="json"),
        "timeseries": series.model_dump(),
    }


@router.get("/events")
def usage_events(
    manager: ConfigManager = Depends(require_admin),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    since: str | None = Query(None),
    until: str | None = Query(None),
    preset: str | None = Query("7d"),
    source: str | None = Query(None),
    user: str | None = Query(None),
    model: str | None = Query(None),
    provider: str | None = Query(None),
    event_type: Literal["llm_call", "tool_call"] | None = Query(None),
    tool_category: str | None = Query(None),
) -> dict[str, Any]:
    filters = _filters_from_query(
        since=since,
        until=until,
        preset=preset,
        source=source,
        user=user,
        model=model,
        provider=provider,
        event_type=event_type,
        tool_category=tool_category,
    )
    page = _store(manager).list_events(filters, limit=limit, offset=offset, pricing=_pricing_table(manager))
    enricher = _enricher(manager)
    return {
        "filters": filters.model_dump(mode="json"),
        "total": page.total,
        "events": [enricher.enrich_event(event.model_dump(mode="json")) for event in page.events],
    }


@router.get("/filters")
def usage_filter_options(
    manager: ConfigManager = Depends(require_admin),
    preset: str | None = Query("30d"),
) -> dict[str, Any]:
    filters = _filters_from_query(
        since=None,
        until=None,
        preset=preset,
        source=None,
        user=None,
        model=None,
        provider=None,
        event_type=None,
        tool_category=None,
    )
    store = _store(manager)
    enricher = _enricher(manager)
    options = store.filter_options(filters)
    users = sorted(
        {
            enricher.display_name(uid, label)
            for uid, label, _count in store.user_breakdown(filters)
        }
    )
    options["users"] = users
    return options


@router.get("/checkpoints")
def get_task_checkpoints(
    task_id: str | None = Query(None),
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    import sqlite3
    from backend.paths import db_path
    db_file = db_path(manager.data_dir)

    # Ensure database table exists
    from backend.observability.checkpoint import init_checkpoint_db
    init_checkpoint_db(db_file)

    conn = sqlite3.connect(db_file, timeout=10.0)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if task_id:
        cursor.execute(
            """
            SELECT checkpoint, function_name, status, timestamp, error, error_stacktrace
            FROM task_checkpoints
            WHERE task_id = ?
            ORDER BY id ASC
            """,
            (task_id,),
        )
    else:
        cursor.execute(
            """
            SELECT task_id, checkpoint, function_name, status, timestamp, error, error_stacktrace
            FROM task_checkpoints
            ORDER BY id DESC
            LIMIT 100
            """
        )
    rows = cursor.fetchall()
    conn.close()

    checkpoints = [dict(r) for r in rows]
    return {"checkpoints": checkpoints}


@router.get("/schedules")
def get_schedules(manager: ConfigManager = Depends(require_admin)) -> dict[str, Any]:
    from backend.db.sqlite_schedule import db_list_schedules
    try:
        jobs = db_list_schedules(manager.data_dir)
        return {"schedules": jobs}
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/schedules/{job_id}/toggle")
def toggle_schedule(
    job_id: str,
    payload: ToggleScheduleRequest,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    from backend.db.sqlite_schedule import db_toggle_schedule
    try:
        success = db_toggle_schedule(manager.data_dir, job_id, payload.active)
        if not success:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Job not found")
        return {"status": "ok"}
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/schedules/{job_id}/trigger")
def trigger_schedule(
    job_id: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    from backend.db.sqlite_schedule import db_list_schedules, db_update_last_run
    from backend.db.sqlite_queue import SQLiteQueue
    from backend.models.task import Task
    from fastapi import HTTPException
    try:
        jobs = db_list_schedules(manager.data_dir)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    job = next((j for j in jobs if j["id"] == job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    try:
        skill_name = job["skill_name"]
        channel_id = job.get("channel_id")
        user_id = job.get("user_id") or "admin_ui"

        task = Task(
            source="scheduler",
            user_id=user_id,
            channel_id=channel_id or "",
            raw_text=f"Manually triggered job {job['name']}",
            cleaned_intent=f"run {skill_name}",
            metadata={
                "job_id": job_id,
                "job_name": job["name"],
                "skill_name": skill_name,
                "manual": True,
            },
        )
        queue = SQLiteQueue(manager.data_dir)
        queue.push(task.model_dump())
        db_update_last_run(manager.data_dir, job_id, "triggered")
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/schedules/{job_id}")
def delete_schedule(
    job_id: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    from backend.db.sqlite_schedule import db_list_schedules, db_delete_schedule
    from backend.paths import playbooks_dir
    try:
        jobs = db_list_schedules(manager.data_dir)
        target = next((j for j in jobs if j["id"] == job_id), None)
        if not target:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Job not found")

        skill_name = target["skill_name"]
        if str(skill_name or "").startswith("scheduled_"):
            p_file = playbooks_dir(manager.data_dir) / f"{skill_name}.md"
            if p_file.exists():
                p_file.unlink()

        db_delete_schedule(manager.data_dir, job_id)
        return {"status": "ok"}
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(exc))


class UpdateScheduleRequest(BaseModel):
    name: str | None = None
    cron_expression: str | None = None
    channel_id: str | None = None
    instructions: str | None = None
    timezone: str | None = None


@router.get("/schedules/{job_id}")
def get_schedule(
    job_id: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    from backend.db.sqlite_schedule import db_list_schedules
    from backend.paths import playbooks_dir
    try:
        jobs = db_list_schedules(manager.data_dir)
        target = next((j for j in jobs if j["id"] == job_id), None)
        if not target:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Job not found")

        # Read instructions from playbook file
        skill_name = target["skill_name"]
        p_file = playbooks_dir(manager.data_dir) / f"{skill_name}.md"
        instructions = ""
        if p_file.exists():
            text = p_file.read_text(encoding="utf-8")
            parts = text.split("# Objective\n")
            if len(parts) > 1:
                instructions = parts[1].strip()

        return {
            **target,
            "instructions": instructions,
        }
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/schedules/{job_id}")
def update_schedule(
    job_id: str,
    payload: UpdateScheduleRequest,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    from backend.db.sqlite_schedule import db_list_schedules, db_update_schedule
    from backend.paths import playbooks_dir
    try:
        jobs = db_list_schedules(manager.data_dir)
        target = next((j for j in jobs if j["id"] == job_id), None)
        if not target:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Job not found")

        # Update DB fields
        desc = None
        if payload.cron_expression is not None:
            desc = f"Triggered by cron: {payload.cron_expression}"

        db_update_schedule(
            manager.data_dir,
            job_id,
            name=payload.name,
            description=desc,
            cron_expression=payload.cron_expression,
            channel_id=payload.channel_id,
            timezone=payload.timezone,
        )

        # Update playbook if instructions/name changed
        if payload.instructions is not None or payload.name is not None:
            skill_name = target["skill_name"]
            p_file = playbooks_dir(manager.data_dir) / f"{skill_name}.md"

            existing_instructions = ""
            if p_file.exists() and payload.instructions is None:
                text = p_file.read_text(encoding="utf-8")
                parts = text.split("# Objective\n")
                if len(parts) > 1:
                    existing_instructions = parts[1].strip()

            final_instructions = payload.instructions if payload.instructions is not None else existing_instructions
            final_name = payload.name if payload.name is not None else target["name"]

            content = (
                "---\n"
                f"name: {skill_name}\n"
                f"description: Scheduled job to {final_name}\n"
                "mode: workflow\n"
                "triggers:\n"
                f"  - run {skill_name}\n"
                "---\n\n"
                "# Objective\n"
                f"{final_instructions}\n"
            )
            p_file.write_text(content, encoding="utf-8")

        return {"status": "ok"}
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/logs")
def get_logs(
    manager: ConfigManager = Depends(require_admin),
    limit: int = 500,
    search: str | None = None,
) -> dict[str, Any]:
    from backend.paths import log_path
    import re
    p_log = log_path(manager.data_dir)
    if not p_log.is_file():
        return {"logs": []}

    try:
        lines = _tail_log_lines(p_log, 1000)

        log_re = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+([A-Z]+)\s+\[([^\]]+)\]\s+(.*)$")

        parsed_logs = []
        current_log = None

        for line in lines:
            line_str = line.rstrip("\n")
            if not line_str.strip():
                continue
            match = log_re.match(line_str)
            if match:
                if current_log:
                    parsed_logs.append(current_log)
                timestamp, level, logger_name, message = match.groups()

                category = "system"
                lower_log = logger_name.lower() + " " + message.lower()
                if "slack" in lower_log or "bolt" in lower_log:
                    category = "slack"
                elif "git" in lower_log or "github" in lower_log or "gitlab" in lower_log:
                    category = "git"

                current_log = {
                    "timestamp": timestamp,
                    "level": level,
                    "module": logger_name,
                    "message": message,
                    "category": category,
                }
            else:
                if current_log:
                    current_log["message"] += "\n" + line_str
                else:
                    parsed_logs.append({
                        "timestamp": "",
                        "level": "INFO",
                        "module": "system",
                        "message": line_str,
                        "category": "system",
                    })

        if current_log:
            parsed_logs.append(current_log)

        if search:
            search_lower = search.lower()
            parsed_logs = [
                log for log in parsed_logs
                if search_lower in log["message"].lower() or search_lower in log["module"].lower()
            ]

        # Return logs in reverse chronological order (newest first)
        return {"logs": parsed_logs[::-1]}
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/audit")
def governance_audit_log(
    manager: ConfigManager = Depends(require_admin),
    limit: int = Query(50, ge=1, le=200),
    tool_name: str | None = Query(None),
    blocked_only: bool = Query(False),
) -> dict[str, Any]:
    from backend.governance.audit import get_audit_store

    entries = get_audit_store(manager.data_dir).list_recent(
        limit=limit,
        tool_name=tool_name or None,
        blocked_only=blocked_only,
    )
    return {"entries": entries, "total": len(entries)}


@router.get("/health")
def observability_health(manager: ConfigManager = Depends(get_manager)) -> dict[str, str]:
    return {"status": "ok", "backend": "sqlite"}


def _tail_log_lines(filepath: Path, n: int = 1000) -> list[str]:
    """Efficiently read the last N lines of a file by seeking from the end."""
    if not filepath.is_file():
        return []
    try:
        with open(filepath, "rb") as f:
            f.seek(0, 2)
            file_size = f.tell()
            chunk_size = 8192
            offset = 0
            lines: list[str] = []
            while len(lines) <= n and offset < file_size:
                offset = min(file_size, offset + chunk_size)
                f.seek(file_size - offset)
                chunk = f.read(offset).decode("utf-8", errors="ignore")
                lines = chunk.splitlines()
            return lines[-n:]
    except Exception:
        # Fallback to simple read if seek fails
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()
            return all_lines[-n:]
