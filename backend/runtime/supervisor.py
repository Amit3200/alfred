"""Background start/stop for Alfred, Vite frontend, and optional Ollama."""

from __future__ import annotations
import requests


import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from backend.config_manager import ConfigManager
from backend.integrations.ollama import service as ollama_service
from backend.paths import ENV_DATA_DIR, log_path, run_dir

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DEFAULT_FRONTEND_PORT = 5173


def _service_pid_file(data_dir: Path, service: str) -> Path:
    return run_dir(data_dir) / f"{service}.pid"


def _service_log(data_dir: Path, service: str) -> Path:
    return run_dir(data_dir) / f"{service}.stdout.log"


def _is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _read_service_pid(data_dir: Path, service: str) -> int | None:
    path = _service_pid_file(data_dir, service)
    if not path.is_file():
        return None
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return None
    return pid if _is_alive(pid) else None


def _write_service_pid(data_dir: Path, service: str, pid: int) -> None:
    _service_pid_file(data_dir, service).write_text(str(pid), encoding="utf-8")


def _clear_service_pid(data_dir: Path, service: str) -> None:
    path = _service_pid_file(data_dir, service)
    if path.is_file():
        path.unlink()


def alfred_running(data_dir: Path) -> int | None:
    return _read_service_pid(data_dir, "alfred")


def frontend_running(data_dir: Path) -> int | None:
    return _read_service_pid(data_dir, "frontend")


def _stop_pid(pid: int, label: str) -> list[str]:
    steps: list[str] = []
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        steps.append(f"Stopped {label} (pid {pid})")
    except ProcessLookupError:
        steps.append(f"{label} process already exited")
        return steps
    except OSError:
        os.kill(pid, signal.SIGTERM)
        steps.append(f"Stopped {label} (pid {pid})")

    for _ in range(20):
        if not _is_alive(pid):
            break
        time.sleep(0.1)
    if _is_alive(pid):
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except OSError:
            os.kill(pid, signal.SIGKILL)
        steps.append(f"Force-killed {label}")
    return steps


def _start_logged_process(
    cmd: list[str],
    *,
    data_dir: Path,
    service: str,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.Popen[Any]:
    log_file = _service_log(data_dir, service)
    log_handle = log_file.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=env,
        cwd=str(cwd) if cwd else None,
    )
    _write_service_pid(data_dir, service, proc.pid)
    return proc


def _wait_for_http(url: str, retries: int = 15) -> bool:
    if "://0.0.0.0:" in url:
        url = url.replace("://0.0.0.0:", "://127.0.0.1:")
    for _ in range(retries):
        time.sleep(0.5)
        try:
            if requests.get(url, timeout=1).status_code == 200:
                return True
        except Exception:
            continue
    return False


def start_all(
    manager: ConfigManager,
    *,
    host: str,
    port: int,
    with_ollama: bool,
    with_frontend: bool = True,
    frontend_port: int = DEFAULT_FRONTEND_PORT,
    model: str | None = None,
) -> dict[str, Any]:
    data_dir = manager.data_dir
    if existing := alfred_running(data_dir):
        return {
            "ok": False,
            "message": f"Alfred already running (pid {existing}). Run: alfred stop",
            "alfred_pid": existing,
        }
    if with_frontend and (existing_fe := frontend_running(data_dir)):
        return {
            "ok": False,
            "message": f"Frontend dev server already running (pid {existing_fe}). Run: alfred stop",
            "frontend_pid": existing_fe,
        }

    steps: list[str] = []
    if with_ollama:
        ollama_status = ollama_service.get_status(model=model)
        if not ollama_status["running"]:
            started = ollama_service.start_ollama()
            if not started.get("ok"):
                return {"ok": False, "message": started.get("message", "Failed to start Ollama.")}
            steps.append("Started Ollama")
        else:
            steps.append("Ollama already running")

    env = os.environ.copy()
    env[ENV_DATA_DIR] = str(data_dir)
    uvicorn_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.api.app:build_app",
        "--factory",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if with_frontend:
        uvicorn_cmd.append("--reload")

    alfred_proc = _start_logged_process(
        uvicorn_cmd,
        data_dir=data_dir,
        service="alfred",
        cwd=PROJECT_ROOT,
        env=env,
    )

    api_url = f"http://{host}:{port}"
    if alfred_proc.poll() is not None or not _wait_for_http(f"{api_url}/api/health"):
        _stop_pid(alfred_proc.pid, "Alfred")
        _clear_service_pid(data_dir, "alfred")
        return {
            "ok": False,
            "message": (
                f"Alfred failed to start. See {_service_log(data_dir, 'alfred')}"
            ),
        }

    steps.append(f"Started Alfred API on {api_url}")

    frontend_url = ""
    frontend_pid: int | None = None
    if with_frontend:
        if not (FRONTEND_DIR / "package.json").is_file():
            _stop_pid(alfred_proc.pid, "Alfred")
            _clear_service_pid(data_dir, "alfred")
            return {"ok": False, "message": f"Frontend not found at {FRONTEND_DIR}"}

        if not (FRONTEND_DIR / "node_modules").is_dir():
            _stop_pid(alfred_proc.pid, "Alfred")
            _clear_service_pid(data_dir, "alfred")
            return {
                "ok": False,
                "message": "Frontend dependencies missing. Run: cd frontend && npm install",
            }

        npm = shutil.which("npm")
        if not npm:
            _stop_pid(alfred_proc.pid, "Alfred")
            _clear_service_pid(data_dir, "alfred")
            return {"ok": False, "message": "npm not found on PATH. Install Node.js to use the dev UI."}

        fe_cmd = [
            npm,
            "run",
            "dev",
            "--",
            "--host",
            host,
            "--port",
            str(frontend_port),
            "--strictPort",
        ]
        fe_proc = _start_logged_process(
            fe_cmd,
            data_dir=data_dir,
            service="frontend",
            cwd=FRONTEND_DIR,
        )
        frontend_url = f"http://{host}:{frontend_port}"
        if fe_proc.poll() is not None or not _wait_for_http(frontend_url):
            _stop_pid(fe_proc.pid, "frontend dev server")
            _clear_service_pid(data_dir, "frontend")
            _stop_pid(alfred_proc.pid, "Alfred")
            _clear_service_pid(data_dir, "alfred")
            return {
                "ok": False,
                "message": (
                    f"Frontend dev server failed to start. See {_service_log(data_dir, 'frontend')}"
                ),
            }
        frontend_pid = fe_proc.pid
        steps.append(f"Started Vite dev UI on {frontend_url}")

    return {
        "ok": True,
        "message": "Alfred dev stack is running.",
        "steps": steps,
        "alfred_pid": alfred_proc.pid,
        "frontend_pid": frontend_pid,
        "url": frontend_url or api_url,
        "api_url": api_url,
        "frontend_url": frontend_url or None,
        "log_file": str(log_path(data_dir)),
        "alfred_stdout_log": str(_service_log(data_dir, "alfred")),
        "frontend_stdout_log": str(_service_log(data_dir, "frontend")) if with_frontend else None,
    }


def stop_all(
    manager: ConfigManager,
    *,
    with_ollama: bool,
    with_frontend: bool = True,
) -> dict[str, Any]:
    data_dir = manager.data_dir
    steps: list[str] = []

    if with_frontend:
        fe_pid = _read_service_pid(data_dir, "frontend")
        if fe_pid is not None:
            steps.extend(_stop_pid(fe_pid, "frontend dev server"))
            _clear_service_pid(data_dir, "frontend")
        else:
            steps.append("Frontend dev server was not running (no pid file)")

    alfred_pid = _read_service_pid(data_dir, "alfred")
    if alfred_pid is not None:
        steps.extend(_stop_pid(alfred_pid, "Alfred"))
        _clear_service_pid(data_dir, "alfred")
    else:
        steps.append("Alfred was not running (no pid file)")

    if with_ollama:
        ollama_result = ollama_service.stop_ollama()
        steps.append(ollama_result.get("message", "Ollama stop attempted"))
        if not ollama_result.get("ok"):
            return {"ok": False, "message": ollama_result.get("message"), "steps": steps}

    return {"ok": True, "message": "Stopped.", "steps": steps}
