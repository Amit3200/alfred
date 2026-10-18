"""Tests for runtime supervisor pid helpers."""

from backend.runtime.supervisor import PROJECT_ROOT, _is_alive, _uvicorn_cmd


def test_is_alive_false_for_invalid_pid():
    assert _is_alive(0) is False
    assert _is_alive(-1) is False
    assert _is_alive(99999999) is False


def test_uvicorn_reload_watches_backend_only():
    cmd = _uvicorn_cmd(host="127.0.0.1", port=8080, reload=True)
    assert "--reload" in cmd
    assert "--reload-dir" in cmd
    idx = cmd.index("--reload-dir")
    assert cmd[idx + 1] == str(PROJECT_ROOT / "backend")
    assert cmd.count("--reload-dir") == 1


def test_uvicorn_without_reload_omits_watch_flags():
    cmd = _uvicorn_cmd(host="127.0.0.1", port=8080, reload=False)
    assert "--reload" not in cmd
    assert "--reload-dir" not in cmd
