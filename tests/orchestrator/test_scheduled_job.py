from pathlib import Path
from unittest.mock import MagicMock

from backend.models.response import AssistantResponse
from backend.models.task import Task
from backend.orchestrator.scheduled_job import playbook_execution_plan, run_scheduled_playbook
from backend.routing.playbooks import Playbook
from backend.tools.result import ToolResult


def test_playbook_execution_plan_from_template():
    playbook = Playbook(
        name="daily_metrics_oneshot",
        path=Path("daily_metrics_oneshot.md"),
        allowed_tools=["run_company_script", "publish_html_artifact"],
        plan_template={
            "goal": "Run metrics",
            "intent_class": "template.daily_metrics_oneshot",
            "steps": [
                {"tool": "run_company_script", "args": {"script": "daily_metrics_oneshot"}},
                {
                    "tool": "publish_html_artifact",
                    "args": {"source_filename": "daily-metrics-latest.html", "slug": "daily-metrics"},
                },
            ],
        },
    )
    plan = playbook_execution_plan(playbook)
    assert plan is not None
    assert plan.tools_needed == ["run_company_script", "publish_html_artifact"]
    assert plan.steps[0].args_hint["script"] == "daily_metrics_oneshot"


def test_run_scheduled_playbook_executes_chain(monkeypatch):
    playbook = Playbook(
        name="daily_metrics_oneshot",
        path=Path("daily_metrics_oneshot.md"),
        allowed_tools=["run_company_script", "publish_html_artifact"],
        plan_template={
            "steps": [
                {"tool": "run_company_script", "args": {"script": "daily_metrics_oneshot"}},
                {
                    "tool": "publish_html_artifact",
                    "args": {"source_filename": "daily-metrics-latest.html", "slug": "daily-metrics"},
                },
            ],
        },
    )
    results = [
        ToolResult(
            kind="company_script_run",
            data={
                "exit_code": 0,
                "json": {
                    "status": "ok",
                    "report_date": "2026-08-17",
                    "publish": {
                        "source_filename": "daily-metrics-latest.html",
                        "slug": "daily-metrics",
                        "title": "Daily metrics — 2026-08-17",
                    },
                },
            },
        ),
        ToolResult(
            kind="html_artifact_published",
            data={
                "slug": "daily-metrics",
                "share_url": "https://alfred.flexype.dev/artifacts/s/daily-metrics",
                "title": "Daily metrics — 2026-08-17",
            },
        ),
    ]
    registry = MagicMock()
    registry.run_normalized.side_effect = results
    monkeypatch.setattr(
        "backend.tools.builder.build_git_tool_registry",
        lambda *args, **kwargs: registry,
    )
    processor = MagicMock()
    processor.config.artifacts.public_base_url = "https://alfred.flexype.dev"
    processor.config.git = MagicMock()
    processor._data_dir_path.return_value = Path(".")
    processor._attach_governance.return_value = None
    task = Task(
        source="scheduler",
        user_id="scheduler",
        channel_id="C1",
        raw_text="Manually triggered job daily_metrics_oneshot",
        cleaned_intent="run scheduled_daily_metrics_oneshot",
    )
    response = run_scheduled_playbook(processor, playbook, task, None)
    assert isinstance(response, AssistantResponse)
    assert registry.run_normalized.call_count == 2
    assert "2026-08-17" in (response.text or "")
    assert "alfred.flexype.dev/artifacts/s/daily-metrics" in (response.text or "")
