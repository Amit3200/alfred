"""Tests for summarize_bugs bundled skill."""

from backend.routing.playbooks import PlaybookStore


def test_summarize_bugs_skill_loads():
    store = PlaybookStore()
    skill = store.get_by_name("summarize_bugs")
    assert skill is not None
    assert skill.mode == "conversational"
    assert skill.bundled is True
    assert "summarize alerts" in skill.triggers


def test_summarize_bugs_matches_alert_summary_intent():
    store = PlaybookStore()
    matched = store.match(
        "can you summarize alerts from the last 7 days by error type?",
        channel_id="C1",
    )
    names = {playbook.name for playbook in matched}
    assert "summarize_bugs" in names


def test_summarize_bugs_not_picked_as_investigation():
    store = PlaybookStore()
    assert store.pick_investigation("summarize bugs last week", channel_id="C1") is None


def test_summarize_bugs_prompt_includes_four_sections():
    store = PlaybookStore()
    skill = store.get_by_name("summarize_bugs")
    assert skill is not None
    prompt = store.format_for_prompt([skill])
    assert "Observations, Trends & Predictions" in prompt
    assert "Resolution & State Tracking" in prompt
    assert "Critical Anomalies & Action Items" in prompt
