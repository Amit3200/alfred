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
    assert "Active playbook" in prompt
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
  - C01234567890
---

Ops channel only.
""",
        encoding="utf-8",
    )
    store = PlaybookStore(tmp_path)
    assert store.match("cpu alert", channel_id="COTHER123456") == []
    assert len(store.match("cpu alert", channel_id="C01234567890")) == 1


def test_playbook_loads_nested_cipher_skills(tmp_path: Path):
    playbooks = tmp_path / "playbooks"
    nested = playbooks / "cipher" / "p0-critical-path"
    nested.mkdir(parents=True)
    (nested / "debug_payment_webhook_failures.md").write_text(
        """---
name: debug_payment_webhook_failures
repos:
  - FlexyPe/cipher
allowed_channels:
  - "#ops-alerts"
trigger_keywords:
  - razorpay webhook
---

Cipher payment runbook.
""",
        encoding="utf-8",
    )
    store = PlaybookStore(tmp_path)
    matched = store.match("razorpay webhook failed")
    assert len(matched) == 1
    assert matched[0].name == "debug_payment_webhook_failures"
    assert matched[0].channels == []


def test_playbook_repo_filter_excludes_other_repos(tmp_path: Path):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "cipher-only.md").write_text(
        """---
name: cipher-only
repos:
  - FlexyPe/cipher
triggers:
  - deploy stack
---

Cipher deploy steps.
""",
        encoding="utf-8",
    )
    store = PlaybookStore(tmp_path)
    assert len(store.match("deploy stack", repo="other-org/other-repo")) == 0
    assert len(store.match("deploy stack", repo="FlexyPe/cipher")) == 1
    assert len(store.match("deploy stack")) == 1


def test_pick_conversational_prefers_longest_trigger(tmp_path: Path):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "short.md").write_text(
        """---
name: short-trigger
triggers:
  - cart
---
Short body.
""",
        encoding="utf-8",
    )
    (playbooks / "long.md").write_text(
        """---
name: long-trigger
triggers:
  - cart total wrong
---
Long body.
""",
        encoding="utf-8",
    )
    store = PlaybookStore(tmp_path)
    picked = store.pick_conversational("cart total wrong after applyCoupon")
    assert picked is not None
    assert picked.name == "long-trigger"


def test_format_catalog_lists_without_bodies(tmp_path: Path):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "secret.md").write_text(
        """---
name: secret-playbook
description: Hidden runbook steps
triggers:
  - secret-keyword
---
This full body must not appear in the catalog.
""",
        encoding="utf-8",
    )
    store = PlaybookStore(tmp_path)
    catalog = store.format_catalog_for_prompt()
    assert "secret-playbook" in catalog
    assert "Hidden runbook steps" in catalog
    assert "This full body must not appear in the catalog." not in catalog


def test_format_routed_prompt_includes_catalog_and_single_active(tmp_path: Path):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "a.md").write_text(
        """---
name: playbook-a
triggers:
  - alpha
---
Alpha instructions.
""",
        encoding="utf-8",
    )
    (playbooks / "b.md").write_text(
        """---
name: playbook-b
triggers:
  - beta
---
Beta instructions.
""",
        encoding="utf-8",
    )
    store = PlaybookStore(tmp_path)
    active = store.pick_conversational("please alpha test")
    prompt = store.format_routed_prompt(active)
    assert "Available playbooks & skills" in prompt
    assert "playbook-a" in prompt
    assert "playbook-b" in prompt
    assert "Alpha instructions." in prompt
    assert "Beta instructions." not in prompt


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
