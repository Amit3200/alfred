"""Admin UI chat — per-window sessions backed by TaskProcessor."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config_manager import ConfigManager
from backend.formatting.chat_export import export_session_markdown, wants_export_markdown
from backend.formatting.render import render_for_channel
from backend.orchestrator.processor import STRUCTURED_TOOL_KINDS, TaskProcessor
from backend.models.session import ConversationSession, session_key_for_task
from backend.models.task import Task
from backend.db.session_store import SessionStore

logger = logging.getLogger(__name__)

UI_SOURCE = "ui"


def ui_session_key(chat_id: str) -> str:
    return session_key_for_task(UI_SOURCE, chat_id, chat_id)


class UIChatService:
    def __init__(self, manager: ConfigManager, queue: Any | None = None) -> None:
        self.manager = manager
        self.queue = queue
        self.store = SessionStore(manager.data_dir)
        config, _ = manager.load_merged()
        self.processor = TaskProcessor(config, session_store=self.store, data_dir=manager.data_dir)

    def list_chats(self) -> list[dict[str, Any]]:
        sessions = self.store.list_by_source(UI_SOURCE)
        return [self._summary(session) for session in sessions]

    def create_chat(self, *, title: str = "New chat") -> dict[str, Any]:
        chat_id = uuid.uuid4().hex[:12]
        session = ConversationSession(
            key=ui_session_key(chat_id),
            source=UI_SOURCE,
            scope_id=chat_id,
            thread_id=chat_id,
            metadata={
                "title": title,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        self.store.save(session)
        return self._summary(session)

    def get_chat(self, chat_id: str) -> dict[str, Any] | None:
        session = self.store.load(ui_session_key(chat_id))
        if session is None:
            return None
        return self._detail(session)

    def delete_chat(self, chat_id: str) -> bool:
        return self.store.delete(ui_session_key(chat_id))

    def send_message(self, chat_id: str, content: str) -> dict[str, Any]:
        session = self.store.load(ui_session_key(chat_id))
        if session is None:
            raise KeyError(f"Chat not found: {chat_id}")

        stripped = content.strip()
        if not stripped:
            raise ValueError("Message cannot be empty")

        if wants_export_markdown(stripped):
            path = export_session_markdown(session, self.manager.data_dir)
            reply = (
                f"Exported this conversation to `{path.name}`.\n\n"
                f"Download: `/api/chat/exports/{path.name}`"
            )
            self.store.append_exchange(
                ui_session_key(chat_id),
                source=UI_SOURCE,
                scope_id=chat_id,
                thread_id=chat_id,
                user_content=stripped,
                assistant_content=reply,
            )
            return {
                "reply": reply,
                "export": {"filename": path.name, "path": str(path)},
                "chat": self.get_chat(chat_id),
            }

        if not session.turns and session.metadata.get("title") == "New chat":
            session.metadata["title"] = _title_from_message(stripped)
            self.store.save(session)

        task = Task(
            source=UI_SOURCE,
            user_id="admin-ui",
            channel_id=chat_id,
            thread_ts=chat_id,
            raw_text=stripped,
            cleaned_intent=stripped,
            metadata={"chat_id": chat_id, "user_label": "Admin UI"},
        )
        if self.queue is not None:
            task_id = self.queue.push(task.model_dump())
            import time
            start_time = time.time()
            # Poll for background task completion
            while time.time() - start_time < 90.0:
                status = self.queue.get_status(task_id)
                if status in ("completed", "failed"):
                    break
                time.sleep(0.5)

            session = self.store.load(ui_session_key(chat_id))
            if session and session.turns:
                last_turn = session.turns[-1]
                if last_turn.role == "assistant":
                    return {
                        "reply": last_turn.content,
                        "payload": last_turn.payload.model_dump() if last_turn.payload else None,
                        "chat": self._detail(session),
                    }
            raise RuntimeError("Task processing timed out or failed in the background queue")
        else:
            response = self.processor.process(task)
            if response.payload.kind in STRUCTURED_TOOL_KINDS and response.text:
                reply = response.text
            else:
                reply = render_for_channel(response, "ui")
            return {
                "reply": reply,
                "payload": response.payload.model_dump(),
                "chat": self.get_chat(chat_id),
            }

    def export_chat(self, chat_id: str, *, filename: str | None = None) -> dict[str, Any]:
        session = self.store.load(ui_session_key(chat_id))
        if session is None:
            raise KeyError(f"Chat not found: {chat_id}")
        path = export_session_markdown(session, self.manager.data_dir, filename=filename)
        return {
            "filename": path.name,
            "path": str(path),
            "download_url": f"/api/chat/exports/{path.name}",
        }

    def _summary(self, session: ConversationSession) -> dict[str, Any]:
        return {
            "id": session.scope_id,
            "title": session.metadata.get("title") or "Chat",
            "message_count": len(session.turns),
            "updated_at": session.metadata.get("updated_at"),
            "created_at": session.metadata.get("created_at"),
        }

    def _detail(self, session: ConversationSession) -> dict[str, Any]:
        data = self._summary(session)
        data["messages"] = [
            {
                "role": t.role,
                "content": t.content,
                "payload": t.payload.model_dump() if t.payload else None,
            }
            for t in session.turns
        ]
        return data


def _title_from_message(text: str) -> str:
    one_line = " ".join(text.split())
    if len(one_line) <= 56:
        return one_line or "New chat"
    return one_line[:53] + "..."
