"""Async UI chat — user message persisted before worker completes."""

from __future__ import annotations

from pathlib import Path

from backend.api.ui_chat import UIChatService
from backend.config_manager import ConfigManager
from backend.db.session_store import SessionStore


class _FakeQueue:
    def __init__(self) -> None:
        self.tasks: list[dict] = []

    def push(self, task: dict) -> str:
        self.tasks.append(task)
        return task.get("id") or "task-test-1"

    def get_status(self, task_id: str) -> str:
        return "running"


def test_send_message_enqueues_and_persists_user_turn(tmp_path: Path):
    manager = ConfigManager(tmp_path)
    manager.init()
    service = UIChatService(manager, queue=_FakeQueue())
    created = service.create_chat(title="Async")
    chat_id = created["id"]

    result = service.send_message(chat_id, "integrate libs/grade with insights-usage")

    assert result["pending"] is True
    assert result["task_id"]
    chat = result["chat"]
    assert len(chat["messages"]) == 1
    assert chat["messages"][0]["role"] == "user"
    assert "integrate" in chat["messages"][0]["content"]


def test_append_exchange_skips_duplicate_user_turn(tmp_path: Path):
    store = SessionStore(tmp_path)
    key = "ui:abc:abc"
    store.append_user_turn(
        key,
        source="ui",
        scope_id="abc",
        thread_id="abc",
        user_content="hello",
    )
    session = store.append_exchange(
        key,
        source="ui",
        scope_id="abc",
        thread_id="abc",
        user_content="hello",
        assistant_content="world",
    )
    assert len(session.turns) == 2
    assert session.turns[0].role == "user"
    assert session.turns[1].role == "assistant"


def test_queue_cancel_pending_task(tmp_path: Path):
    from backend.db.sqlite_queue import SQLiteQueue

    queue = SQLiteQueue(tmp_path)
    task_id = queue.push({"id": "task-1", "source": "ui", "cleaned_intent": "hello"})
    assert queue.get_status(task_id) == "pending"
    assert queue.cancel(task_id) is True
    assert queue.get_status(task_id) == "cancelled"
    assert queue.cancel(task_id) is False


def test_find_active_task_for_ui_chat(tmp_path: Path):
    from backend.db.sqlite_queue import SQLiteQueue

    queue = SQLiteQueue(tmp_path)
    older = queue.push(
        {
            "id": "task-old",
            "source": "ui",
            "channel_id": "chat-a",
            "cleaned_intent": "old",
        }
    )
    newer = queue.push(
        {
            "id": "task-new",
            "source": "ui",
            "channel_id": "chat-a",
            "cleaned_intent": "new",
        }
    )
    assert queue.find_active_task(source="ui", channel_id="chat-a") == newer
    queue.cancel(older)
    assert queue.find_active_task(source="ui", channel_id="chat-a") == newer
    queue.cancel(newer)
    assert queue.find_active_task(source="ui", channel_id="chat-a") is None
