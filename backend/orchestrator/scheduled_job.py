"""Deterministic execution for cron / Admin Run now — no ReAct tool-manifest hop."""

from __future__ import annotations

import logging
from typing import Any

from backend.models.response import AssistantResponse
from backend.models.session import ConversationSession, mirror_workspace_key
from backend.models.task import Task
from backend.routing.playbooks import Playbook
from backend.routing.tool_plan_types import ToolPlan, ToolPlanStep
from backend.routing.workflow_chain import plan_from_playbook_chain

logger = logging.getLogger(__name__)


def playbook_execution_plan(playbook: Playbook) -> ToolPlan | None:
    """Build a tool plan from a playbook's plan_template or workflow_chain."""
    template = playbook.plan_template if isinstance(playbook.plan_template, dict) else {}
    steps_raw = template.get("steps") if template else None
    if isinstance(steps_raw, list) and steps_raw:
        steps: list[ToolPlanStep] = []
        tools: list[str] = []
        for item in steps_raw:
            if not isinstance(item, dict):
                continue
            tool = str(item.get("tool") or "").strip()
            if not tool:
                continue
            if tool not in tools:
                tools.append(tool)
            args_hint: dict[str, Any] = {}
            if isinstance(item.get("args"), dict):
                args_hint.update(item["args"])
            steps.append(
                ToolPlanStep(
                    tool=tool,
                    purpose=str(item.get("purpose") or playbook.description or playbook.name),
                    args_hint=args_hint,
                )
            )
        if tools:
            return ToolPlan(
                goal=str(template.get("goal") or playbook.description or playbook.name),
                confidence=0.99,
                tools_needed=tools,
                steps=steps,
                intent_class=str(template.get("intent_class") or f"template.{playbook.name}"),
                strategy="scheduled_playbook",
            )
    return plan_from_playbook_chain(playbook)


def _script_payload(result_data: dict[str, Any]) -> dict[str, Any]:
    parsed = result_data.get("json")
    return parsed if isinstance(parsed, dict) else result_data


def _enrich_publish_args(args: dict[str, Any], script_data: dict[str, Any]) -> dict[str, Any]:
    publish = script_data.get("publish")
    if not isinstance(publish, dict):
        publish = {}
    merged = dict(args)
    for key in ("source_filename", "slug", "title"):
        value = str(merged.get(key) or publish.get(key) or "").strip()
        if value:
            merged[key] = value
    return merged


def _format_scheduled_reply(
    *,
    skill: Playbook,
    script_data: dict[str, Any] | None,
    publish_data: dict[str, Any] | None,
    public_base_url: str,
) -> str:
    from backend.artifacts.formatting import format_published_artifact_slack

    lines: list[str] = []
    if publish_data:
        lines.append(format_published_artifact_slack(publish_data, public_base_url=public_base_url))
    if script_data:
        report_date = str(script_data.get("report_date") or "").strip()
        status = str(script_data.get("status") or "").strip()
        if report_date:
            title = f"Daily metrics — {report_date} (IST)"
            if status == "ok":
                title += " ✅"
            elif status:
                title += f" ({status})"
            lines.insert(0, f"*{title}*")
        failed = script_data.get("sections_failed") or script_data.get("oneshot", {})
        if isinstance(failed, dict):
            failed = failed.get("sections_failed")
        if failed:
            lines.append(f"Failed sections: {failed}")
    if not lines:
        lines.append(f"Scheduled job `{skill.name}` finished.")
    return "\n".join(lines)


def run_scheduled_playbook(
    processor: Any,
    skill: Playbook,
    task: Task,
    session: ConversationSession | None,
) -> AssistantResponse | None:
    """Run the playbook's tools in order. Returns None if the playbook has no executable plan."""
    plan = playbook_execution_plan(skill)
    if plan is None or not plan.steps:
        logger.info("Scheduled job %s has no executable plan; falling back to agent", skill.name)
        return None

    from backend.tools.builder import build_git_tool_registry

    tools = list(dict.fromkeys([*(skill.allowed_tools or []), *plan.tools_needed]))
    registry = build_git_tool_registry(
        processor.config,
        workspace_id=mirror_workspace_key(task),
        data_dir=processor._data_dir_path(),
        allowed_tools=tools or None,
    )
    processor._attach_governance(registry, task, session=session, skill_name=skill.name)

    script_data: dict[str, Any] | None = None
    publish_data: dict[str, Any] | None = None
    for step in plan.steps:
        args = dict(step.args_hint or {})
        if step.tool == "publish_html_artifact" and script_data:
            args = _enrich_publish_args(args, script_data)
        logger.info("Scheduled job %s → %s", skill.name, step.tool)
        result = registry.run_normalized(
            step.tool,
            args,
            allowed=tools,
            git=processor.config.git,
            session=session,
        )
        if result.kind == "error":
            message = str(result.data.get("message") or f"{step.tool} failed.")
            return AssistantResponse.error(f"Scheduled `{skill.name}` failed on `{step.tool}`: {message}")
        if result.kind == "company_script_run":
            script_data = _script_payload(result.data or {})
            if int((result.data or {}).get("exit_code") or 0) != 0:
                tail = str((result.data or {}).get("stderr") or "")[-800:]
                return AssistantResponse.error(
                    f"Scheduled `{skill.name}` script exited "
                    f"{(result.data or {}).get('exit_code')}. {tail}".strip()
                )
        if result.kind == "html_artifact_published":
            publish_data = result.data or {}

    public_base = str(getattr(processor.config.artifacts, "public_base_url", "") or "").strip()
    return AssistantResponse.from_text(
        _format_scheduled_reply(
            skill=skill,
            script_data=script_data,
            publish_data=publish_data,
            public_base_url=public_base,
        )
    )
