"""Background cron scheduler service for Alfred."""

from __future__ import annotations

import datetime
import logging
import threading
import time
from pathlib import Path
from typing import Any

from backend.config_manager import ConfigManager
from backend.db.sqlite_queue import SQLiteQueue
from backend.db.sqlite_schedule import db_list_schedules, db_update_last_run
from backend.models.task import Task

logger = logging.getLogger(__name__)


def cron_matches(cron_expr: str, dt: datetime.datetime) -> bool:
    """Check if the given datetime matches the cron expression."""
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return False

    def match_field(val: int, pattern: str, min_val: int, max_val: int) -> bool:
        if pattern == "*":
            return True
        if "," in pattern:
            return any(match_field(val, p, min_val, max_val) for p in pattern.split(","))
        step = 1
        if "/" in pattern:
            pattern, step_str = pattern.split("/")
            step = int(step_str)
        if pattern == "*":
            low, high = min_val, max_val
        elif "-" in pattern:
            low_str, high_str = pattern.split("-")
            low, high = int(low_str), int(high_str)
        else:
            low = high = int(pattern)
        return low <= val <= high and (val - low) % step == 0

    # Map Monday=0 -> 1, ..., Saturday=5 -> 6, Sunday=6 -> 0
    cron_weekday = (dt.weekday() + 1) % 7
    weekday_pattern = parts[4]
    if weekday_pattern == "7":
        weekday_pattern = "0"
    elif ",7" in weekday_pattern or "7," in weekday_pattern:
        weekday_pattern = weekday_pattern.replace(",7", ",0").replace("7,", "0,")

    return (
        match_field(dt.minute, parts[0], 0, 59) and
        match_field(dt.hour, parts[1], 0, 23) and
        match_field(dt.day, parts[2], 1, 31) and
        match_field(dt.month, parts[3], 1, 12) and
        match_field(cron_weekday, weekday_pattern, 0, 6)
    )


class SchedulerService:
    """Thread-based service that runs periodically and matches cron tasks to execute."""

    def __init__(self, manager: ConfigManager, queue: SQLiteQueue) -> None:
        self.manager = manager
        self.queue = queue
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.running = False

    def start(self) -> None:
        """Start the background scheduler thread."""
        if self.running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="alfred-scheduler",
            daemon=True,
        )
        self._thread.start()
        self.running = True
        logger.info("Alfred cron scheduler service started")

    def stop(self) -> None:
        """Stop the background scheduler thread."""
        if not self.running:
            return
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        self.running = False
        logger.info("Alfred cron scheduler service stopped")

    def _run_loop(self) -> None:
        last_minute = -1
        while not self._stop_event.is_set():
            now = datetime.datetime.now()
            if now.minute != last_minute:
                last_minute = now.minute
                self._check_and_trigger_jobs(now)
            # Sleep in small chunks to allow quick shutdown
            for _ in range(10):
                if self._stop_event.is_set():
                    break
                time.sleep(1.0)

    def _check_and_trigger_jobs(self, dt: datetime.datetime) -> None:
        try:
            schedules = db_list_schedules(self.manager.data_dir)
        except Exception:
            logger.exception("Failed to load schedules from database")
            return

        for job in schedules:
            if job.get("status") != "active":
                continue

            cron_expr = job.get("cron_expression") or ""
            if not cron_expr:
                continue

            tz_name = job.get("timezone") or "Asia/Kolkata"
            try:
                from zoneinfo import ZoneInfo
                local_dt = dt.astimezone()
                tz_dt = local_dt.astimezone(ZoneInfo(tz_name))
            except Exception:
                logger.exception("Failed to evaluate timezone %s, using server local time", tz_name)
                tz_dt = dt

            if cron_matches(cron_expr, tz_dt):
                job_id = job["id"]
                skill_name = job["skill_name"]
                channel_id = job.get("channel_id")
                user_id = job.get("user_id") or "scheduler"
                logger.info("Triggering scheduled job %s (%s)", job["name"], cron_expr)

                try:
                    task = Task(
                        source="scheduler",
                        user_id=user_id,
                        channel_id=channel_id or "",
                        raw_text=f"Run scheduled job {job['name']}",
                        cleaned_intent=f"run {skill_name}",
                        metadata={
                            "job_id": job_id,
                            "job_name": job["name"],
                            "skill_name": skill_name,
                        },
                    )
                    self.queue.push(task.model_dump())
                    db_update_last_run(self.manager.data_dir, job_id, "triggered")
                except Exception:
                    logger.exception("Failed to enqueue scheduled task for job %s", job_id)
                    try:
                        db_update_last_run(self.manager.data_dir, job_id, "failed")
                    except Exception:
                        pass
