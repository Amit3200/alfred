"""Tests for domain playbook loading."""

from pathlib import Path

from backend.ingress.playbooks import PlaybookStore


def test_playbook_matches_trigger(tmp_path: Path):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "summaries.md").write_text(
        """---
name: slack-summaries
triggers:
  - summarize
  - merchant
---

# Instructions
Include every row in a code block table.
""",
        encoding="utf-8",
    )
    store = PlaybookStore(tmp_path)
    matched = store.match("can you summarize June merchants?", channel_id="C1")
    assert len(matched) == 1
    assert matched[0].name == "slack-summaries"
    prompt = store.format_for_prompt(matched)
    assert "Domain playbooks" in prompt
    assert "code block table" in prompt


def test_playbook_respects_channel_filter(tmp_path: Path):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "scoped.md").write_text(
        """---
name: ops-only
triggers:
  - alert
channels:
  - COPS
---

Ops channel only.
""",
        encoding="utf-8",
    )
    store = PlaybookStore(tmp_path)
    assert store.match("cpu alert", channel_id="COTHER") == []
    assert len(store.match("cpu alert", channel_id="COPS")) == 1


def test_playbook_parses_investigation_skill_fields(tmp_path: Path):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "git.md").write_text(
        """---
name: git-test
mode: investigation
triggers:
  - show my prs
allowed_tools:
  - list_my_prs
requires_thread_context: false
---

Use tools.
""",
        encoding="utf-8",
    )
    store = PlaybookStore(tmp_path)
    skill = store.pick_investigation("show my prs please")
    assert skill is not None
    assert skill.mode == "investigation"
    assert skill.allowed_tools == ["list_my_prs"]
