"""Tests for smart playbook/skill routing (catalog vs loaded body)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from backend.ingress.processor import TaskProcessor
from backend.ingress.playbooks import PlaybookStore
from backend.models.config import default_config
from backend.models.task import Task


def test_processor_loads_one_playbook_when_many_triggers_match(tmp_path: Path):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "payment.md").write_text(
        """---
name: debug_payment
triggers:
  - payment webhook
  - webhook
---
Payment runbook body.
""",
        encoding="utf-8",
    )
    (playbooks / "order.md").write_text(
        """---
name: debug_order
triggers:
  - shopify order
  - order
---
Order runbook body.
""",
        encoding="utf-8",
    )

    config = default_config()
    mock_provider = MagicMock()
    mock_provider.chat.return_value = MagicMock(content="ok", model="m")

    processor = TaskProcessor(config, data_dir=tmp_path)
    processor.router = MagicMock()
    processor.router.get.return_value = mock_provider

    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C01234567890",
        thread_ts="1.0",
        raw_text="@alfred payment webhook failing",
        cleaned_intent="payment webhook failing",
    )
    processor.process(task)

    system = mock_provider.chat.call_args.args[0][0].content
    assert "Payment runbook body." in system
    assert "Order runbook body." not in system
    assert "debug_payment" in system
    assert "debug_order" in system


def test_processor_catalog_only_when_no_trigger_match(tmp_path: Path):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "scoped.md").write_text(
        """---
name: scoped-playbook
triggers:
  - very-specific-keyword
---
Scoped body.
""",
        encoding="utf-8",
    )

    config = default_config()
    mock_provider = MagicMock()
    mock_provider.chat.return_value = MagicMock(content="ok", model="m")

    processor = TaskProcessor(config, data_dir=tmp_path)
    processor.router = MagicMock()
    processor.router.get.return_value = mock_provider

    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C01234567890",
        thread_ts="1.0",
        raw_text="@alfred hello team",
        cleaned_intent="hello team",
    )
    processor.process(task)

    system = mock_provider.chat.call_args.args[0][0].content
    assert "Available playbooks & skills" in system
    assert "scoped-playbook" in system
    assert "Scoped body." not in system
    assert "## Active playbook (loaded for this request)" not in system


def test_investigation_skill_body_without_conversational_stack(tmp_path: Path):
    store = PlaybookStore(tmp_path)
    inv = store.get_by_name("investigate_bug")
    assert inv is not None
    picked = store.pick_investigation("where is recalculateSession handled?")
    assert picked is not None
    assert picked.name == "investigate_bug"
    conv = store.pick_conversational("where is recalculateSession handled?")
    assert conv is None or conv.mode == "conversational"
