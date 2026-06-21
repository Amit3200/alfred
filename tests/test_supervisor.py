"""Tests for runtime supervisor pid helpers."""

from backend.runtime.supervisor import _is_alive


def test_is_alive_false_for_invalid_pid():
    assert _is_alive(0) is False
    assert _is_alive(-1) is False
    assert _is_alive(99999999) is False
