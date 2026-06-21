"""Tests for processor playbook injection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from backend.ingress.processor import TaskProcessor
from backend.models.config import default_config
from backend.models.task import Task


def test_processor_injects_matched_playbook(tmp_path: Path):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "summaries.md").write_text(
        """---
name: test-playbook
triggers:
  - unique-summarize-keyword
---

Always include a code block table.
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
        channel_id="C1",
        thread_ts="1.0",
        raw_text="@alfred summarize alerts",
        cleaned_intent="unique-summarize-keyword for merchants",
    )
    processor.process(task)

    messages = mock_provider.chat.call_args.args[0]
    system = messages[0].content
    assert "Available playbooks & skills" in system
    assert "## Active playbook (loaded for this request)" in system
    assert "code block table" in system
