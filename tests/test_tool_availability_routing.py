"""Routing skips playbooks whose allowed tools are missing or disabled."""

from __future__ import annotations

from pathlib import Path

from backend.models.config import AlfredConfig, default_config
from backend.routing import RouteContext, RouteMode, SkillRouter
from backend.routing.heuristics import route_by_heuristic
from backend.routing.tool_availability import playbook_has_runnable_tools


def test_playbook_has_runnable_tools_rejects_unknown_tool():
    config = default_config()
    assert not playbook_has_runnable_tools(["grade_events_query"], config)


def test_playbook_has_runnable_tools_accepts_athena():
    config = default_config()
    config.aws.enabled = True
    assert playbook_has_runnable_tools(["athena_query"], config)


def test_router_skips_stale_playbook_and_falls_back_to_heuristic(tmp_path: Path):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "stale.md").write_text(
        """---
name: grade_events
mode: investigation
triggers: [grade events]
allowed_tools: [grade_events_query]
---
body
""",
        encoding="utf-8",
    )

    from backend.routing.playbooks import PlaybookStore

    store = PlaybookStore(tmp_path)
    config = default_config()
    config.git.enabled = True

    router = SkillRouter(config, store, llm_router=None)
    result = router.route_investigation(
        RouteContext(
            intent="Using grade events in cipher - libs/grade integrate with libs/insights-usage",
            mode=RouteMode.INVESTIGATION,
        )
    )
    assert result.playbook is not None
    assert result.playbook.name == "investigate_bug"
    assert result.decision.strategy == "heuristic"


def test_heuristic_matches_raise_pr_anywhere(tmp_path: Path):
    from backend.routing.playbooks import PlaybookStore

    store = PlaybookStore(tmp_path)
    config = default_config()
    config.git.enabled = True
    config.git.write_enabled = True
    decision = route_by_heuristic(
        RouteContext(
            intent="Looks good — can we raise a PR for it?",
            mode=RouteMode.INVESTIGATION,
        ),
        store,
        config,
    )
    assert decision.skill_name == "create_pr"


def test_create_pr_routes_trigger_pr_followup(tmp_path: Path):
    from backend.routing.playbooks import PlaybookStore

    store = PlaybookStore(tmp_path)
    config = default_config()
    config.git.enabled = True
    config.git.write_enabled = True
    router = SkillRouter(config, store, llm_router=None)
    result = router.route_investigation(
        RouteContext(
            intent="can you trigger the pr change then as per above?",
            mode=RouteMode.INVESTIGATION,
            session_turns=(
                "Would you like me to proceed with committing and opening the draft PR?",
            ),
        )
    )
    assert result.playbook is not None
    assert result.playbook.name == "create_pr"
    assert result.decision.strategy in ("heuristic", "keyword")


def test_create_pr_routes_before_git_status_pr_keyword(tmp_path: Path):
    from backend.routing.playbooks import PlaybookStore

    store = PlaybookStore(tmp_path)
    config = default_config()
    config.git.enabled = True
    config.git.write_enabled = True
    router = SkillRouter(config, store, llm_router=None)
    result = router.route_investigation(
        RouteContext(
            intent="Can you try creating PR?",
            mode=RouteMode.INVESTIGATION,
        )
    )
    assert result.playbook is not None
    assert result.playbook.name == "create_pr"


def test_create_pr_wins_over_grade_events_when_both_mentioned(tmp_path: Path):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "grade-events.md").write_text(
        """---
name: grade_events
mode: investigation
triggers: [grade events]
allowed_tools: [athena_query, grep_repo]
---
body
""",
        encoding="utf-8",
    )
    from backend.routing.playbooks import PlaybookStore

    store = PlaybookStore(tmp_path)
    config = default_config()
    config.git.enabled = True
    config.git.write_enabled = True
    config.aws.enabled = True
    router = SkillRouter(config, store, llm_router=None)
    result = router.route_investigation(
        RouteContext(
            intent=(
                "Using grade events in cipher integrate libs/insights-usage with libs/grade. "
                "Can we raise a PR for it?"
            ),
            mode=RouteMode.INVESTIGATION,
        )
    )
    assert result.playbook is not None
    assert result.playbook.name == "create_pr"
