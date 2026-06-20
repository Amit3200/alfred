"""Tests for conversation session storage."""

from __future__ import annotations

from backend.models.session import session_key_for_task
from backend.storage.session_store import SessionStore


def test_session_key_isolation():
    k1 = session_key_for_task("slack", "C1", "111.1")
    k2 = session_key_for_task("slack", "C1", "222.2")
    k3 = session_key_for_task("slack", "C2", "111.1")
    assert k1 != k2
    assert k1 != k3


def test_session_store_append_exchange(tmp_path):
    store = SessionStore(tmp_path)
    key = session_key_for_task("slack", "C1", "111.1")
    store.append_exchange(
        key,
        source="slack",
        scope_id="C1",
        thread_id="111.1",
        user_content="hello",
        assistant_content="hi there",
        context_snapshot="channel: alert",
    )
    loaded = store.load(key)
    assert loaded is not None
    assert len(loaded.turns) == 2
    assert loaded.turns[0].content == "hello"
    assert loaded.context_snapshot == "channel: alert"

    store.append_exchange(
        key,
        source="slack",
        scope_id="C1",
        thread_id="111.1",
        user_content="try again",
        assistant_content="sure",
    )
    loaded2 = store.load(key)
    assert loaded2 is not None
    assert len(loaded2.turns) == 4
