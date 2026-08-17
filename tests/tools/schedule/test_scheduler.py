import datetime
from pathlib import Path
import tempfile
import pytest

from backend.runtime.scheduler import cron_matches
from backend.db.sqlite_schedule import (
    db_create_schedule,
    db_list_schedules,
    db_delete_schedule,
    db_toggle_schedule,
    db_update_last_run,
    db_update_schedule,
    db_get_schedule,
)
from backend.tools.registry import ToolRegistry
from backend.tools.schedule.register import register_schedule_tools


def test_cron_matches():
    # 2026-07-05 15:30:00 (Sunday)
    # python dt.weekday() returns 6 (Sunday)
    dt = datetime.datetime(2026, 7, 5, 15, 30, 0)

    # Sunday in cron is 0 (or 7)
    assert cron_matches("30 15 * * *", dt) is True
    assert cron_matches("30 15 * * 0", dt) is True
    assert cron_matches("30 15 * * 7", dt) is True
    assert cron_matches("*/5 15 * * *", dt) is True
    assert cron_matches("30 15-18 * * *", dt) is True
    assert cron_matches("30 15 * * 1-5", dt) is False
    assert cron_matches("0 15 * * *", dt) is False


def test_db_schedule_crud():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)

        # Initially empty
        jobs = db_list_schedules(data_dir)
        assert len(jobs) == 0

        # Create
        db_create_schedule(
            data_dir=data_dir,
            job_id="test_id_1",
            name="Test Job 1",
            description="Run every hour",
            cron_expression="0 * * * *",
            skill_name="test_skill_1",
            channel_id="C12345",
            user_id="U999",
            timezone="UTC",
        )

        jobs = db_list_schedules(data_dir)
        assert len(jobs) == 1
        assert jobs[0]["id"] == "test_id_1"
        assert jobs[0]["status"] == "active"
        assert jobs[0]["cron_expression"] == "0 * * * *"
        assert jobs[0]["timezone"] == "UTC"

        # Get detailed schedule
        detail = db_get_schedule(data_dir, "test_id_1")
        assert detail is not None
        assert detail["name"] == "Test Job 1"

        # Update schedule
        success = db_update_schedule(
            data_dir=data_dir,
            job_id="test_id_1",
            name="Updated Job Name",
            cron_expression="*/5 * * * *",
            channel_id="C999",
            timezone="America/New_York",
        )
        assert success is True

        updated = db_get_schedule(data_dir, "test_id_1")
        assert updated["name"] == "Updated Job Name"
        assert updated["cron_expression"] == "*/5 * * * *"
        assert updated["channel_id"] == "C999"
        assert updated["timezone"] == "America/New_York"

        # Toggle inactive
        success = db_toggle_schedule(data_dir, "test_id_1", False)
        assert success is True
        jobs = db_list_schedules(data_dir)
        assert jobs[0]["status"] == "inactive"

        # Toggle active
        db_toggle_schedule(data_dir, "test_id_1", True)
        jobs = db_list_schedules(data_dir)
        assert jobs[0]["status"] == "active"

        # Update last run
        db_update_last_run(data_dir, "test_id_1", "success")
        jobs = db_list_schedules(data_dir)
        assert jobs[0]["last_run_status"] == "success"
        assert jobs[0]["last_run_at"] is not None

        # Delete
        deleted = db_delete_schedule(data_dir, "test_id_1")
        assert deleted is True
        jobs = db_list_schedules(data_dir)
        assert len(jobs) == 0


def test_schedule_tools():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        registry = ToolRegistry()
        register_schedule_tools(registry, data_dir)

        # Verify registration
        schemas = registry.get_schemas(["create_schedule", "list_schedules", "toggle_schedule", "delete_schedule", "update_schedule"])
        assert len(schemas) == 5

        # Run list_schedules tool
        res = registry.run("list_schedules", {}, allowed=["list_schedules"])
        assert res.kind == "success"
        assert "schedules" in res.data
        assert len(res.data["schedules"]) == 0

        # Run create_schedule tool
        res_create = registry.run(
            "create_schedule",
            {
                "name": "My Scheduled Action",
                "cron_expression": "*/10 * * * *",
                "instructions": "Log the current load and CPU usage",
                "channel_id": "C555",
                "timezone": "Europe/London",
            },
            allowed=["create_schedule"],
        )
        assert res_create.kind == "success"
        assert "job_id" in res_create.data
        job_id = res_create.data["job_id"]

        # Run update_schedule tool
        res_update = registry.run(
            "update_schedule",
            {
                "job_id": job_id,
                "name": "Modified Action Name",
                "cron_expression": "0 0 * * *",
                "instructions": "New workflow instructions content",
                "timezone": "UTC",
            },
            allowed=["update_schedule"],
        )
        assert res_update.kind == "success"

        # Check DB lists 1 job now
        res_list = registry.run("list_schedules", {}, allowed=["list_schedules"])
        assert len(res_list.data["schedules"]) == 1
        job = res_list.data["schedules"][0]
        assert job["name"] == "Modified Action Name"
        assert job["cron_expression"] == "0 0 * * *"
        assert job["timezone"] == "UTC"

        # Toggle schedule tool
        res_toggle = registry.run(
            "toggle_schedule",
            {"job_id": job["id"], "active": False},
            allowed=["toggle_schedule"],
        )
        assert res_toggle.kind == "success"

        # Check toggle reflection
        res_list = registry.run("list_schedules", {}, allowed=["list_schedules"])
        assert res_list.data["schedules"][0]["status"] == "inactive"

        # Delete schedule tool
        res_delete = registry.run(
            "delete_schedule",
            {"job_id": job["id"]},
            allowed=["delete_schedule"],
        )
        assert res_delete.kind == "success"

        # Check deletion reflection
        res_list = registry.run("list_schedules", {}, allowed=["list_schedules"])
        assert len(res_list.data["schedules"]) == 0
