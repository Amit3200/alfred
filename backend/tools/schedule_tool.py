"""Tool schemas and handlers for managing scheduled jobs and playbooks."""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any

from backend.ai.base import ToolSchema
from backend.db.sqlite_schedule import (
    db_create_schedule,
    db_delete_schedule,
    db_list_schedules,
    db_toggle_schedule,
)
from backend.paths import playbooks_dir
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult

logger = logging.getLogger(__name__)

CREATE_SCHEDULE = ToolSchema(
    name="create_schedule",
    description=(
        "Create a new scheduled cron job to run a set of instructions on a matching schedule "
        "and generate a reusable skill playbook for it."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Short human-readable name for the job (e.g. checkout_error_report).",
            },
            "cron_expression": {
                "type": "string",
                "description": "Standard 5-field cron pattern (e.g. '0 9 * * 1-5' for Mon-Fri 9:00am).",
            },
            "instructions": {
                "type": "string",
                "description": "Specific step-by-step instructions or prompt of what the job should do.",
            },
            "channel_id": {
                "type": "string",
                "description": "Optional Slack channel ID to post the execution result to.",
            },
        },
        "required": ["name", "cron_expression", "instructions"],
    },
)

LIST_SCHEDULES = ToolSchema(
    name="list_schedules",
    description="List all scheduled jobs configured in the system.",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)

TOGGLE_SCHEDULE = ToolSchema(
    name="toggle_schedule",
    description="Enable or disable a scheduled job.",
    parameters={
        "type": "object",
        "properties": {
            "job_id": {
                "type": "string",
                "description": "The unique ID of the scheduled job.",
            },
            "active": {
                "type": "boolean",
                "description": "Set to true to activate the job, false to deactivate.",
            },
        },
        "required": ["job_id", "active"],
    },
)

DELETE_SCHEDULE = ToolSchema(
    name="delete_schedule",
    description="Delete a scheduled job configuration and clean up its generated skill playbook.",
    parameters={
        "type": "object",
        "properties": {
            "job_id": {
                "type": "string",
                "description": "The unique ID of the scheduled job to delete.",
            },
        },
        "required": ["job_id"],
    },
)


def register_schedule_tools(registry: ToolRegistry, data_dir: Path | None) -> None:
    """Register all job scheduling tools in the tool registry."""

    def create_schedule_handler(args: dict[str, Any]) -> ToolResult:
        name = str(args.get("name") or "").strip()
        cron_expr = str(args.get("cron_expression") or "").strip()
        instructions = str(args.get("instructions") or "").strip()
        channel_id = args.get("channel_id")

        if not name or not cron_expr or not instructions:
            return ToolResult.error("name, cron_expression, and instructions are required.")

        # Normalize name to snake_case slug
        slug = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")
        if not slug:
            slug = f"job_{uuid.uuid4().hex[:8]}"

        skill_name = f"scheduled_{slug}"
        job_id = f"job_{uuid.uuid4().hex[:12]}"

        # Write playbook skill file
        try:
            p_dir = playbooks_dir(data_dir)
            p_dir.mkdir(parents=True, exist_ok=True)
            p_file = p_dir / f"{skill_name}.md"

            content = (
                "---\n"
                f"name: {skill_name}\n"
                f"description: Scheduled job to {name}\n"
                "mode: workflow\n"
                "triggers:\n"
                f"  - run {skill_name}\n"
                "---\n\n"
                "# Objective\n"
                f"{instructions}\n"
            )
            p_file.write_text(content, encoding="utf-8")
            logger.info("Created scheduled skill playbook at %s", p_file)
        except Exception as exc:
            return ToolResult.error(f"Failed to generate playbook skill file: {exc}")

        # Save to database
        try:
            db_create_schedule(
                data_dir=data_dir,
                job_id=job_id,
                name=name,
                description=f"Triggered by cron: {cron_expr}",
                cron_expression=cron_expr,
                skill_name=skill_name,
                channel_id=channel_id,
                user_id="scheduler",
            )
        except Exception as exc:
            # Clean up playbook file on DB failure
            if p_file.exists():
                p_file.unlink()
            return ToolResult.error(f"Failed to save schedule to database: {exc}")

        return ToolResult(
            kind="success",
            data={
                "message": f"Successfully created schedule job '{name}' (ID: {job_id})",
                "job_id": job_id,
                "cron": cron_expr,
                "skill_name": skill_name,
            }
        )

    def list_schedules_handler(_args: dict[str, Any]) -> ToolResult:
        try:
            jobs = db_list_schedules(data_dir)
            return ToolResult(kind="success", data={"schedules": jobs})
        except Exception as exc:
            return ToolResult.error(f"Failed to query schedules from database: {exc}")

    def toggle_schedule_handler(args: dict[str, Any]) -> ToolResult:
        job_id = str(args.get("job_id") or "").strip()
        active = bool(args.get("active"))

        if not job_id:
            return ToolResult.error("job_id is required.")

        try:
            success = db_toggle_schedule(data_dir, job_id, active)
            if not success:
                return ToolResult.error(f"Job ID {job_id} not found.")
            action = "activated" if active else "deactivated"
            return ToolResult(kind="success", data={"message": f"Successfully {action} job {job_id}"})
        except Exception as exc:
            return ToolResult.error(f"Failed to update schedule status: {exc}")

    def delete_schedule_handler(args: dict[str, Any]) -> ToolResult:
        job_id = str(args.get("job_id") or "").strip()
        if not job_id:
            return ToolResult.error("job_id is required.")

        try:
            jobs = db_list_schedules(data_dir)
            target_job = next((j for j in jobs if j["id"] == job_id), None)
            if not target_job:
                return ToolResult.error(f"Job ID {job_id} not found.")

            # Delete file
            skill_name = target_job["skill_name"]
            p_file = playbooks_dir(data_dir) / f"{skill_name}.md"
            if p_file.exists():
                p_file.unlink()
                logger.info("Deleted scheduled skill playbook at %s", p_file)

            # Delete DB row
            db_delete_schedule(data_dir, job_id)
            return ToolResult(kind="success", data={"message": f"Successfully deleted scheduled job {job_id}"})
        except Exception as exc:
            return ToolResult.error(f"Failed to delete schedule: {exc}")

    registry.register(CREATE_SCHEDULE, create_schedule_handler)
    registry.register(LIST_SCHEDULES, list_schedules_handler)
    registry.register(TOGGLE_SCHEDULE, toggle_schedule_handler)
    registry.register(DELETE_SCHEDULE, delete_schedule_handler)
