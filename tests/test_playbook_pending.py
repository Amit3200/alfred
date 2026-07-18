"""Tests for self-learning playbook review queue."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.models.task import Task
from backend.orchestrator.playbook_pending import (
    approve_pending_playbook,
    enqueue_pending_playbook,
    list_pending_playbooks,
    reject_pending_playbook,
)
from backend.paths import playbooks_dir


def _task() -> Task:
    return Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        thread_ts="1",
        raw_text="@alfred why deploy failing",
        cleaned_intent="why is deployment failing",
    )


def test_enqueue_and_approve_pending_playbook(tmp_path: Path):
    task = _task()
    content = "---\nname: deploy_debug\ntriggers: [deploy]\n---\n# Debug deploy\n"
    pending_id = enqueue_pending_playbook(
        task=task,
        proposed_content=content,
        playbook_name="deploy_debug",
        data_dir=tmp_path,
    )
    pending = list_pending_playbooks(tmp_path)
    assert len(pending) == 1
    assert pending[0]["id"] == pending_id

    result = approve_pending_playbook(tmp_path, pending_id)
    assert result["filename"] == "deploy_debug.md"
    assert (playbooks_dir(tmp_path) / "deploy_debug.md").is_file()
    assert list_pending_playbooks(tmp_path) == []


def test_reject_pending_playbook(tmp_path: Path):
    pending_id = enqueue_pending_playbook(
        task=_task(),
        proposed_content="---\nname: x\ntriggers: [x]\n---\nbody\n",
        playbook_name="x_playbook",
        data_dir=tmp_path,
    )
    reject_pending_playbook(tmp_path, pending_id)
    assert list_pending_playbooks(tmp_path) == []
    assert not any(playbooks_dir(tmp_path).glob("*.md"))


def test_approve_conflict_when_playbook_exists(tmp_path: Path):
    playbooks_dir(tmp_path).mkdir(parents=True)
    (playbooks_dir(tmp_path) / "deploy_debug.md").write_text("existing\n", encoding="utf-8")
    pending_id = enqueue_pending_playbook(
        task=_task(),
        proposed_content="---\nname: deploy_debug\ntriggers: [deploy]\n---\nnew\n",
        playbook_name="deploy_debug",
        data_dir=tmp_path,
    )
    with pytest.raises(FileExistsError):
        approve_pending_playbook(tmp_path, pending_id)
