"""Scheduled job tools — schemas live here; handlers use ToolContext."""

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
from backend.tools.base.function_tool import FunctionTool
from backend.tools.base.tool import BaseTool, ToolContext
from backend.tools.result import ToolResult

logger = logging.getLogger(__name__)

_SCHEDULE_PLAYBOOK_TOOLS = (
    "run_company_script",
    "list_company_scripts",
    "athena_query",
    "cloudwatch_query",
    "list_cloudwatch_log_groups",
    "save_html_deck",
    "publish_html_artifact",
)


def _schedule_playbook_frontmatter(skill_name: str, title: str) -> str:
    tools_yaml = "".join(f"  - {tool}\n" for tool in _SCHEDULE_PLAYBOOK_TOOLS)
    return (
        "---\n"
        f"name: {skill_name}\n"
        f"description: Scheduled job — {title}\n"
        "mode: workflow\n"
        "triggers:\n"
        f"  - run {skill_name}\n"
        "allowed_tools:\n"
        f"{tools_yaml}"
        "---\n"
    )


def _schedule_playbook_body(instructions: str) -> str:
    return (
        "# Objective\n"
        f"{instructions}\n\n"
        "# Execution\n"
        "1. Prefer **`run_company_script`** when instructions name a script under "
        "`.alfred/scripts/` — pass structured `args`, do not rewrite the script logic.\n"
        "2. For ad-hoc AWS reads, use `athena_query` / `cloudwatch_query` with LIMIT and "
        "partition filters documented in your domain playbooks.\n"
        "3. Reply in Slack with a concise summary and key numbers; attach tables when useful.\n"
    )


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
            "timezone": {
                "type": "string",
                "description": (
                    "Optional timezone to evaluate the cron expression "
                    "(e.g. 'Asia/Kolkata', 'UTC'). Default is 'Asia/Kolkata'."
                ),
            },
        },
        "required": ["name", "cron_expression", "instructions"],
    },
)

LIST_SCHEDULES = ToolSchema(
    name="list_schedules",
    description="List all scheduled jobs configured in the system.",
    parameters={"type": "object", "properties": {}, "required": []},
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

UPDATE_SCHEDULE = ToolSchema(
    name="update_schedule",
    description=(
        "Update an existing scheduled job configuration "
        "(name, cron expression, channel ID, timezone, or instructions)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "job_id": {
                "type": "string",
                "description": "The unique ID of the scheduled job to update.",
            },
            "name": {"type": "string", "description": "Optional new name for the job."},
            "cron_expression": {
                "type": "string",
                "description": "Optional new cron pattern (e.g. '0 12 * * *').",
            },
            "channel_id": {
                "type": "string",
                "description": (
                    "Optional new Slack channel ID to post results to "
                    "(pass empty string or null to clear)."
                ),
            },
            "instructions": {
                "type": "string",
                "description": "Optional new instructions / playbook content.",
            },
            "timezone": {
                "type": "string",
                "description": "Optional new timezone (e.g. 'UTC').",
            },
        },
        "required": ["job_id"],
    },
)


def _require_data_dir(ctx: ToolContext) -> Path | ToolResult:
    if ctx.data_dir is None:
        return ToolResult.error("data_dir is required for schedule tools.")
    return ctx.data_dir


def create_schedule(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    data_dir = _require_data_dir(ctx)
    if isinstance(data_dir, ToolResult):
        return data_dir

    name = str(args.get("name") or "").strip()
    cron_expr = str(args.get("cron_expression") or "").strip()
    instructions = str(args.get("instructions") or "").strip()
    channel_id = args.get("channel_id")
    timezone = str(args.get("timezone") or "Asia/Kolkata").strip()

    if not name or not cron_expr or not instructions:
        return ToolResult.error("name, cron_expression, and instructions are required.")

    slug = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")
    if not slug:
        slug = f"job_{uuid.uuid4().hex[:8]}"

    skill_name = f"scheduled_{slug}"
    job_id = f"job_{uuid.uuid4().hex[:12]}"

    try:
        p_dir = playbooks_dir(data_dir)
        p_dir.mkdir(parents=True, exist_ok=True)
        p_file = p_dir / f"{skill_name}.md"
        content = _schedule_playbook_frontmatter(skill_name, name) + "\n" + _schedule_playbook_body(
            instructions
        )
        p_file.write_text(content, encoding="utf-8")
        logger.info("Created scheduled skill playbook at %s", p_file)
    except Exception as exc:
        return ToolResult.error(f"Failed to generate playbook skill file: {exc}")

    try:
        jobs = db_list_schedules(data_dir)
        existing = next((j for j in jobs if j["skill_name"] == skill_name), None)
        if existing:
            job_id = existing["id"]

        db_create_schedule(
            data_dir=data_dir,
            job_id=job_id,
            name=name,
            description=f"Triggered by cron: {cron_expr}",
            cron_expression=cron_expr,
            skill_name=skill_name,
            channel_id=channel_id,
            user_id="scheduler",
            timezone=timezone,
        )
    except Exception as exc:
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
        },
    )


def list_schedules(ctx: ToolContext, _args: dict[str, Any]) -> ToolResult:
    data_dir = _require_data_dir(ctx)
    if isinstance(data_dir, ToolResult):
        return data_dir
    try:
        jobs = db_list_schedules(data_dir)
        return ToolResult(kind="success", data={"schedules": jobs})
    except Exception as exc:
        return ToolResult.error(f"Failed to query schedules from database: {exc}")


def toggle_schedule(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    data_dir = _require_data_dir(ctx)
    if isinstance(data_dir, ToolResult):
        return data_dir
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


def delete_schedule(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    data_dir = _require_data_dir(ctx)
    if isinstance(data_dir, ToolResult):
        return data_dir
    job_id = str(args.get("job_id") or "").strip()
    if not job_id:
        return ToolResult.error("job_id is required.")
    try:
        jobs = db_list_schedules(data_dir)
        target_job = next((j for j in jobs if j["id"] == job_id), None)
        if not target_job:
            return ToolResult.error(f"Job ID {job_id} not found.")
        skill_name = target_job["skill_name"]
        p_file = playbooks_dir(data_dir) / f"{skill_name}.md"
        if p_file.exists():
            p_file.unlink()
            logger.info("Deleted scheduled skill playbook at %s", p_file)
        db_delete_schedule(data_dir, job_id)
        return ToolResult(kind="success", data={"message": f"Successfully deleted scheduled job {job_id}"})
    except Exception as exc:
        return ToolResult.error(f"Failed to delete schedule: {exc}")


def update_schedule(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    data_dir = _require_data_dir(ctx)
    if isinstance(data_dir, ToolResult):
        return data_dir
    job_id = str(args.get("job_id") or "").strip()
    name = args.get("name")
    cron_expr = args.get("cron_expression")
    channel_id = args.get("channel_id")
    instructions = args.get("instructions")
    timezone = args.get("timezone")
    if not job_id:
        return ToolResult.error("job_id is required.")

    from backend.db.sqlite_schedule import db_update_schedule

    try:
        jobs = db_list_schedules(data_dir)
        target = next((j for j in jobs if j["id"] == job_id), None)
        if not target:
            return ToolResult.error(f"Schedule job with ID {job_id} not found.")

        desc = f"Triggered by cron: {cron_expr}" if cron_expr is not None else None
        db_update_schedule(
            data_dir=data_dir,
            job_id=job_id,
            name=name,
            description=desc,
            cron_expression=cron_expr,
            channel_id=channel_id,
            timezone=timezone,
        )

        if instructions is not None or name is not None:
            skill_name = target["skill_name"]
            p_file = playbooks_dir(data_dir) / f"{skill_name}.md"
            existing_instructions = ""
            if p_file.exists() and instructions is None:
                text = p_file.read_text(encoding="utf-8")
                parts = text.split("# Objective\n")
                if len(parts) > 1:
                    existing_instructions = parts[1].strip()
            final_instructions = instructions if instructions is not None else existing_instructions
            final_name = name if name is not None else target["name"]
            content = (
                _schedule_playbook_frontmatter(skill_name, final_name)
                + "\n"
                + _schedule_playbook_body(final_instructions)
            )
            p_file.write_text(content, encoding="utf-8")

        return ToolResult(
            kind="success",
            data={"message": f"Successfully updated schedule job '{job_id}'", "job_id": job_id},
        )
    except Exception as exc:
        return ToolResult.error(f"Failed to update schedule: {exc}")


def schedule_tools() -> list[BaseTool]:
    return [
        FunctionTool(
            name="create_schedule",
            capability="schedule.write.create",
            operation="create",
            domain="schedule",
            schema=CREATE_SCHEDULE,
            run_fn=create_schedule,
            produces=("job_id", "skill_name"),
            next_tools=("list_schedules",),
        ),
        FunctionTool(
            name="list_schedules",
            capability="schedule.read.list",
            operation="list",
            domain="schedule",
            schema=LIST_SCHEDULES,
            run_fn=list_schedules,
            produces=("schedules",),
            next_tools=("create_schedule", "toggle_schedule"),
        ),
        FunctionTool(
            name="toggle_schedule",
            capability="schedule.write.toggle",
            operation="toggle",
            domain="schedule",
            schema=TOGGLE_SCHEDULE,
            run_fn=toggle_schedule,
            consumes=("job_id",),
        ),
        FunctionTool(
            name="delete_schedule",
            capability="schedule.write.delete",
            operation="delete",
            domain="schedule",
            schema=DELETE_SCHEDULE,
            run_fn=delete_schedule,
            consumes=("job_id",),
        ),
        FunctionTool(
            name="update_schedule",
            capability="schedule.write.update",
            operation="update",
            domain="schedule",
            schema=UPDATE_SCHEDULE,
            run_fn=update_schedule,
            consumes=("job_id",),
        ),
    ]
