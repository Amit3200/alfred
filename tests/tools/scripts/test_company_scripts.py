"""Tests for company scripts catalog and tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.integrations.company_scripts.catalog import CompanyScriptStore, seed_example_scripts
from backend.integrations.company_scripts.runner import apply_alfred_aws_env, run_company_script
from backend.models.config import AWSConfig, AlfredConfig, ScriptsConfig
from backend.tools.scripts.register import register_company_script_tools
from backend.tools.registry import ToolRegistry


def test_seed_and_list_scripts(tmp_path: Path):
    seed_example_scripts(tmp_path)
    store = CompanyScriptStore(tmp_path)
    scripts = store.list_scripts()
    assert any(s.name == "daily_error_summary" for s in scripts)
    script = store.get("daily_error_summary")
    assert script is not None
    assert script.args
    assert any(a.name == "date" and a.required for a in script.args)


def test_apply_alfred_aws_env_overrides_process_profile():
    env = {"AWS_PROFILE": "dataops-limited", "AWS_DEFAULT_PROFILE": "dataops-limited"}
    config = AlfredConfig(
        aws=AWSConfig(
            enabled=True,
            profile="dataops",
            region="ap-south-1",
            athena_database="dataops",
            athena_workgroup="primary",
            athena_output_location="s3://dataops.athena/athena/queries/",
        )
    )
    apply_alfred_aws_env(config, env)
    assert env["AWS_PROFILE"] == "dataops"
    assert env["AWS_DEFAULT_PROFILE"] == "dataops"
    assert env["AWS_REGION"] == "ap-south-1"
    assert env["ATHENA_OUTPUT_LOCATION"] == "s3://dataops.athena/athena/queries/"


def test_run_company_script_echo(tmp_path: Path):
    seed_example_scripts(tmp_path)
    config = AlfredConfig(scripts=ScriptsConfig(enabled=True, timeout_seconds=30))
    data = run_company_script(
        config,
        script_name="daily_error_summary",
        args={"date": "2026-06-20", "environment": "staging"},
        data_dir=tmp_path,
    )
    assert data["exit_code"] == 0
    assert "2026-06-20" in data["stdout"]
    assert data["json"]["environment"] == "staging"


def test_run_company_script_missing_required_arg(tmp_path: Path):
    seed_example_scripts(tmp_path)
    config = AlfredConfig(scripts=ScriptsConfig(enabled=True))
    with pytest.raises(ValueError, match="Missing required arg"):
        run_company_script(config, script_name="daily_error_summary", args={}, data_dir=tmp_path)


def test_playbook_scripts_prompt(tmp_path: Path):
    from backend.routing.playbooks import PlaybookStore

    seed_example_scripts(tmp_path)
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "checkout.md").write_text(
        "---\nname: checkout\ntriggers:\n  - checkout\nscripts:\n  - daily_error_summary\n---\n\nBody\n",
        encoding="utf-8",
    )
    store = PlaybookStore(tmp_path)
    skill = store.get_by_name("checkout")
    assert skill is not None
    assert skill.scripts == ["daily_error_summary"]
    prompt = store.format_for_prompt([skill], data_dir=tmp_path)
    assert "daily_error_summary" in prompt
    assert "run_company_script" in prompt


def test_company_script_tools_registered(tmp_path: Path):
    registry = ToolRegistry()
    config = AlfredConfig(scripts=ScriptsConfig(enabled=True))
    register_company_script_tools(registry, config=config, data_dir=tmp_path)
    assert "run_company_script" in registry._tools
    seed_example_scripts(tmp_path)
    result = registry.run(
        "run_company_script",
        {"script": "daily_error_summary", "args": {"date": "2026-06-01"}},
        allowed=["run_company_script"],
    )
    assert result.kind == "company_script_run"


def test_company_script_write_tools(tmp_path: Path):
    registry = ToolRegistry()
    config = AlfredConfig(scripts=ScriptsConfig(enabled=True, timeout_seconds=30))
    register_company_script_tools(registry, config=config, data_dir=tmp_path)

    created = registry.run(
        "create_company_script_package",
        {
            "package_path": "ops/nightly",
            "runtime": "python3",
            "description": "Nightly rollup",
            "entry": "main.py",
        },
        allowed=["create_company_script_package"],
    )
    assert created.kind == "company_script_package"
    assert created.data["package"]["name"] == "ops/nightly"

    updated = registry.run(
        "write_company_script_file",
        {
            "relative_path": "ops/nightly/main.py",
            "content": (
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "args = json.loads(sys.argv[1] if len(sys.argv) > 1 else '{}')\n"
                "print(json.dumps({'ok': True, 'date': args.get('date')}))\n"
            ),
        },
        allowed=["write_company_script_file"],
    )
    assert updated.kind == "company_script_write"

    read_back = registry.run(
        "read_company_script_file",
        {"relative_path": "ops/nightly/main.py"},
        allowed=["read_company_script_file"],
    )
    assert read_back.kind == "company_script_file"
    assert "json.dumps" in read_back.data["content"]

    manifest = registry.run(
        "write_company_script_file",
        {
            "relative_path": "ops/nightly/script.yaml",
            "content": (
                "name: ops/nightly\n"
                "description: Nightly rollup\n"
                "entry: main.py\n"
                "runtime: python3\n"
                "args:\n"
                "  - name: date\n"
                "    required: true\n"
            ),
        },
        allowed=["write_company_script_file"],
    )
    assert manifest.kind == "company_script_write"

    run_result = registry.run(
        "run_company_script",
        {"script": "ops/nightly", "args": {"date": "2026-07-01"}},
        allowed=["run_company_script"],
    )
    assert run_result.kind == "company_script_run"
    assert run_result.data["json"]["date"] == "2026-07-01"


def test_schedule_playbook_includes_script_tools():
    from backend.tools.schedule.register import _schedule_playbook_frontmatter

    text = _schedule_playbook_frontmatter("scheduled_daily_report", "Daily report")
    assert "run_company_script" in text
    assert "allowed_tools:" in text


def test_nested_script_package(tmp_path: Path):
    pkg = tmp_path / "scripts" / "checkout" / "daily_report"
    pkg.mkdir(parents=True)
    (pkg / "script.yaml").write_text(
        "name: checkout/daily_report\n"
        "description: Nested checkout rollup\n"
        "entry: main.py\n"
        "runtime: python3\n"
        "args:\n"
        "  - name: date\n"
        "    required: true\n",
        encoding="utf-8",
    )
    (pkg / "main.py").write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "args = json.loads(sys.argv[1] if len(sys.argv) > 1 else '{}')\n"
        "print(json.dumps({'date': args.get('date')}))\n",
        encoding="utf-8",
    )
    store = CompanyScriptStore(tmp_path)
    script = store.get("checkout/daily_report")
    assert script is not None
    assert script.name == "checkout/daily_report"
    assert store.get("checkout__daily_report") is not None
    assert "main.py" in store.list_package_files("checkout/daily_report")

    config = AlfredConfig(scripts=ScriptsConfig(enabled=True, timeout_seconds=30))
    data = run_company_script(
        config,
        script_name="checkout/daily_report",
        args={"date": "2026-01-01"},
        data_dir=tmp_path,
    )
    assert data["exit_code"] == 0
    assert data["json"]["date"] == "2026-01-01"
