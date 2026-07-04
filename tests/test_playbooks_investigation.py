"""Tests for investigation skill selection."""

from backend.routing.playbooks import PlaybookStore


def test_pick_investigation_prefers_review_pr_over_git_status():
    store = PlaybookStore()
    skill = store.pick_investigation(
        "please review pr https://github.com/org/repo/pull/1",
        channel_id="C1",
    )
    assert skill is not None
    assert skill.name == "review_pr"
    assert "get_pr_changes" in skill.allowed_tools
