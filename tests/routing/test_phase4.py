"""Phase 4 — capability bundles, plan templates, phrase routing, routing traces."""

from __future__ import annotations

from pathlib import Path

import yaml

from backend.models.config import AlfredConfig, RoutingConfig
from backend.routing.capabilities import bundle_tools, load_capability_bundles, resolve_bundle_for_tools
from backend.routing.engine import SkillRouter
from backend.routing.plan_templates import match_plan_template
from backend.routing.playbooks import Playbook, PlaybookStore, _parse_playbook_index
from backend.routing.trace_store import build_trace_record, get_trace, list_traces, record_trace
from backend.routing.types import RouteContext, RouteMode


def test_load_default_capability_bundles():
    bundles = load_capability_bundles()
    assert "jira" in bundles
    assert "get_jira_issue" in bundles["jira"].tools
    assert bundles["jira"].policy_name == "jira_management"


def test_custom_capabilities_yaml(tmp_path: Path):
    path = tmp_path / "capabilities.yaml"
    path.write_text(
        yaml.dump(
            {
                "bundles": {
                    "custom": {
                        "tools": ["grep_repo", "read_file"],
                        "policy_name": "investigate_bug",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    bundles = load_capability_bundles(tmp_path)
    assert "custom" in bundles
    assert bundle_tools("custom", data_dir=tmp_path) == ["grep_repo", "read_file"]


def test_resolve_bundle_for_tools():
    name = resolve_bundle_for_tools(["jira_search", "get_jira_issue"])
    assert name == "jira"


def test_parse_policy_playbook_frontmatter(tmp_path: Path):
    path = tmp_path / "jira_policy.md"
    path.write_text(
        """---
name: jira_policy
type: policy
mode: investigation
capability_bundle: jira
output:
  format: jira_summary
---
# JIRA policy
""",
        encoding="utf-8",
    )
    pb = _parse_playbook_index(path, bundled=False)
    assert pb.playbook_type == "policy"
    assert pb.capability_bundle == "jira"
    assert pb.output_format == "jira_summary"


def test_plan_template_match(tmp_path: Path, monkeypatch):
    playbooks_dir = tmp_path / "playbooks"
    playbooks_dir.mkdir()
    (playbooks_dir / "redirect_report.md").write_text(
        """---
name: redirect_report
type: plan_template
triggers:
  - redirect metrics
plan_template:
  goal: Build redirect metrics report
  steps:
    - tool: run_company_script
      args: { script: redirect_metrics }
    - tool: google_create_sheet
---
""",
        encoding="utf-8",
    )
    empty_skills = tmp_path / "empty_skills"
    empty_skills.mkdir()
    monkeypatch.setattr("backend.routing.playbooks.bundled_skills_dir", lambda: empty_skills)
    monkeypatch.setattr("backend.routing.playbooks.playbooks_dir", lambda _data: playbooks_dir)

    store = PlaybookStore(data_dir=tmp_path)
    plan = match_plan_template("show me redirect metrics for yesterday", store)
    assert plan is not None
    assert plan.strategy == "plan_template"
    assert "run_company_script" in plan.tools_needed


def test_match_plan_template_injects_named_date(tmp_path: Path, monkeypatch):
    playbooks_dir = tmp_path / "playbooks"
    playbooks_dir.mkdir()
    (playbooks_dir / "daily_metrics_oneshot.md").write_text(
        """---
name: daily_metrics_oneshot
type: plan_template
triggers:
  - daily metrics oneshot
plan_template:
  goal: Run daily metrics
  steps:
    - tool: run_company_script
      args: { script: daily_metrics_oneshot }
---
""",
        encoding="utf-8",
    )
    empty_skills = tmp_path / "empty_skills"
    empty_skills.mkdir()
    monkeypatch.setattr("backend.routing.playbooks.bundled_skills_dir", lambda: empty_skills)
    monkeypatch.setattr("backend.routing.playbooks.playbooks_dir", lambda _data: playbooks_dir)

    store = PlaybookStore(data_dir=tmp_path)
    plan = match_plan_template("run daily metrics oneshot for 2026-08-16", store)
    assert plan is not None
    script_step = next(s for s in plan.steps if s.tool == "run_company_script")
    assert script_step.args_hint["script"] == "daily_metrics_oneshot"
    assert script_step.args_hint["args"]["date"] == "2026-08-16"
    assert "2026-08-16" in plan.goal


def test_match_plan_template_skips_create_schedule_request(tmp_path: Path, monkeypatch):
    playbooks_dir = tmp_path / "playbooks"
    playbooks_dir.mkdir()
    (playbooks_dir / "daily_metrics_oneshot.md").write_text(
        """---
name: daily_metrics_oneshot
type: plan_template
triggers:
  - daily metrics oneshot
plan_template:
  goal: Run daily metrics
  steps:
    - tool: run_company_script
      args: { script: daily_metrics_oneshot }
---
""",
        encoding="utf-8",
    )
    empty_skills = tmp_path / "empty_skills"
    empty_skills.mkdir()
    monkeypatch.setattr("backend.routing.playbooks.bundled_skills_dir", lambda: empty_skills)
    monkeypatch.setattr("backend.routing.playbooks.playbooks_dir", lambda _data: playbooks_dir)

    store = PlaybookStore(data_dir=tmp_path)
    plan = match_plan_template(
        "Create a schedule for 6 AM IST to call daily metrics oneshot",
        store,
    )
    assert plan is None


def test_phrase_routing_disabled_skips_investigation_keyword(tmp_path: Path, monkeypatch):
    empty_skills = tmp_path / "empty_skills"
    empty_skills.mkdir()
    monkeypatch.setattr("backend.routing.playbooks.bundled_skills_dir", lambda: empty_skills)

    store = PlaybookStore(data_dir=tmp_path)
    config = AlfredConfig()
    config.routing.phrase_routing_enabled = False
    config.skills.agentic_routing = False

    router = SkillRouter(config, store, llm_router=None)
    ctx = RouteContext(
        intent="summarize alerts in channel",
        mode=RouteMode.INVESTIGATION,
    )
    result = router.route(ctx)
    assert result.playbook is None


def test_routing_trace_store(tmp_path: Path):
    record = build_trace_record(
        task_id="task-1",
        intent="list my jira tickets",
        skill_name="jira_management",
        routing_strategy="rules",
        scoped_tools=["jira_search"],
    )
    record_trace(tmp_path, record)
    traces = list_traces(tmp_path, limit=10)
    assert len(traces) == 1
    assert traces[0]["task_id"] == "task-1"
    found = get_trace(tmp_path, "task-1")
    assert found is not None
    assert found["skill_name"] == "jira_management"


def test_routing_config_defaults():
    routing = RoutingConfig()
    assert routing.phrase_routing_enabled is False
    assert routing.plan_template_min_confidence == 0.7


def test_resolve_policy_skill_uses_plan_template_playbook(tmp_path: Path, monkeypatch):
    playbooks_dir = tmp_path / "playbooks"
    playbooks_dir.mkdir()
    (playbooks_dir / "daily_metrics_oneshot.md").write_text(
        """---
name: daily_metrics_oneshot
mode: workflow
type: plan_template
allowed_tools:
  - run_company_script
  - publish_html_artifact
plan_template:
  intent_class: template.daily_metrics_oneshot
  steps:
    - tool: run_company_script
    - tool: publish_html_artifact
---
# body
""",
        encoding="utf-8",
    )
    empty_skills = tmp_path / "empty_skills"
    empty_skills.mkdir()
    monkeypatch.setattr("backend.routing.playbooks.bundled_skills_dir", lambda: empty_skills)
    monkeypatch.setattr("backend.routing.playbooks.playbooks_dir", lambda _data: playbooks_dir)

    from backend.orchestrator.graph.skill_policy import resolve_policy_skill
    from backend.routing.tool_plan_types import ToolPlan

    store = PlaybookStore(data_dir=tmp_path)
    plan = ToolPlan(
        goal="publish daily metrics",
        confidence=0.9,
        tools_needed=["run_company_script", "publish_html_artifact"],
        intent_class="template.daily_metrics_oneshot",
        strategy="plan_template",
    )
    skill = resolve_policy_skill(plan, store, fallback=None)
    assert skill is not None
    assert skill.name == "daily_metrics_oneshot"


def test_resolve_policy_skill_keeps_script_playbook_for_script_run(tmp_path: Path, monkeypatch):
    playbooks_dir = tmp_path / "playbooks"
    playbooks_dir.mkdir()
    (playbooks_dir / "daily_metrics_oneshot.md").write_text(
        """---
name: daily_metrics_oneshot
mode: workflow
allowed_tools:
  - run_company_script
  - publish_html_artifact
---
# body
""",
        encoding="utf-8",
    )
    (playbooks_dir / "investigate_bug.md").write_text(
        """---
name: investigate_bug
mode: investigation
allowed_tools:
  - grep_repo
  - athena_query
  - web_search
---
# body
""",
        encoding="utf-8",
    )
    empty_skills = tmp_path / "empty_skills"
    empty_skills.mkdir()
    monkeypatch.setattr("backend.routing.playbooks.bundled_skills_dir", lambda: empty_skills)
    monkeypatch.setattr("backend.routing.playbooks.playbooks_dir", lambda _data: playbooks_dir)

    from backend.orchestrator.graph.skill_policy import resolve_policy_skill
    from backend.routing.tool_plan_types import ToolPlan

    store = PlaybookStore(data_dir=tmp_path)
    fallback = store.get_by_name("daily_metrics_oneshot")
    plan = ToolPlan(
        goal="Run company script",
        confidence=0.99,
        tools_needed=["run_company_script"],
        intent_class="script.run",
        strategy="llm",
    )
    skill = resolve_policy_skill(plan, store, fallback=fallback)
    assert skill is not None
    assert skill.name == "daily_metrics_oneshot"
