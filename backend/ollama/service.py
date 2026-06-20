"""Ollama local AI — detect, install, and manage models."""

from __future__ import annotations

import platform
import shutil
import subprocess
import time
from typing import Any

import requests

DEFAULT_MODEL = "llama3"
DEFAULT_BASE_URL = "http://127.0.0.1:11434"


def _api_root(base_url: str | None = None) -> str:
    raw = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    if raw.endswith("/v1"):
        raw = raw[:-3]
    return raw.rstrip("/")


def _run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def get_status(base_url: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Return Ollama install/runtime status."""
    target_model = model or DEFAULT_MODEL
    cli = shutil.which("ollama")
    root = _api_root(base_url)
    running = False
    models: list[str] = []
    error = ""

    if cli:
        try:
            resp = requests.get(f"{root}/api/tags", timeout=5)
            if resp.status_code == 200:
                running = True
                payload = resp.json()
                for item in payload.get("models", []):
                    name = item.get("name", "")
                    if name:
                        models.append(name)
            else:
                error = f"API returned HTTP {resp.status_code}"
        except requests.RequestException as exc:
            error = str(exc)
    else:
        error = "Ollama CLI not found on PATH"

    model_ready = any(
        m == target_model or m.startswith(f"{target_model}:") for m in models
    )

    install_hint = _install_hint()

    return {
        "ok": bool(cli and running),
        "installed": bool(cli),
        "running": running,
        "cli_path": cli,
        "api_url": root,
        "models": models,
        "recommended_model": target_model,
        "model_ready": model_ready,
        "local_only": True,
        "isolated": True,
        "platform": platform.system(),
        "install_hint": install_hint,
        "message": _status_message(cli, running, model_ready, target_model, error),
        "error": error or None,
    }


def _status_message(
    cli: str | None,
    running: bool,
    model_ready: bool,
    model: str,
    error: str,
) -> str:
    if not cli:
        return "Ollama is not installed. Install it to run AI locally — no cloud required."
    if not running:
        return "Ollama is installed but not running. Start the Ollama app or run: ollama serve"
    if not model_ready:
        return f"Ollama is running. Pull a model to get started (e.g. {model})."
    return f"Ready — {model} is available locally."


def _install_hint() -> str:
    system = platform.system()
    if system == "Darwin":
        if shutil.which("brew"):
            return "brew install ollama"
        return "Download from https://ollama.com/download (macOS)"
    if system == "Linux":
        return "curl -fsSL https://ollama.com/install.sh | sh"
    return "Download from https://ollama.com/download"


def install_ollama() -> dict[str, Any]:
    """Install Ollama using platform package manager or official script."""
    if shutil.which("ollama"):
        return {"ok": True, "message": "Ollama is already installed.", "already_installed": True}

    system = platform.system()
    if system == "Darwin":
        if not shutil.which("brew"):
            return {
                "ok": False,
                "message": "Homebrew not found. Download Ollama from https://ollama.com/download",
                "manual_url": "https://ollama.com/download",
            }
        result = _run(["brew", "install", "ollama"], timeout=900)
    elif system == "Linux":
        result = _run(["bash", "-c", "curl -fsSL https://ollama.com/install.sh | sh"], timeout=900)
    else:
        return {
            "ok": False,
            "message": f"Automatic install not supported on {system}. Use https://ollama.com/download",
            "manual_url": "https://ollama.com/download",
        }

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Install failed").strip()
        return {"ok": False, "message": detail[:500]}

    return {
        "ok": True,
        "message": "Ollama installed. Start it with: ollama serve (or open the Ollama app on macOS).",
        "next_step": "start",
    }


def start_ollama() -> dict[str, Any]:
    """Ensure Ollama server is reachable; start background serve if needed."""
    status = get_status()
    if status["running"]:
        return {"ok": True, "message": "Ollama is already running.", "already_running": True}

    if not status["installed"]:
        return {"ok": False, "message": "Install Ollama first."}

    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        return {"ok": False, "message": str(exc)}

    for _ in range(15):
        time.sleep(1)
        if get_status()["running"]:
            return {"ok": True, "message": "Ollama server started locally."}

    return {
        "ok": False,
        "message": "Could not reach Ollama. On macOS, open the Ollama app from Applications.",
    }


def pull_model(model: str | None = None) -> dict[str, Any]:
    """Pull a model via ollama CLI."""
    name = model or DEFAULT_MODEL
    if not shutil.which("ollama"):
        return {"ok": False, "message": "Ollama CLI not installed."}

    if not get_status(model=name)["running"]:
        started = start_ollama()
        if not started.get("ok"):
            return started

    result = _run(["ollama", "pull", name], timeout=3600)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "pull failed").strip()
        return {"ok": False, "message": detail[:500]}

    return {"ok": True, "message": f"Model {name} pulled and ready.", "model": name}


def setup_local(model: str | None = None) -> dict[str, Any]:
    """Install (if needed), start, and pull default model."""
    name = model or DEFAULT_MODEL
    steps: list[dict[str, Any]] = []

    status = get_status(model=name)
    if not status["installed"]:
        install_result = install_ollama()
        steps.append({"step": "install", **install_result})
        if not install_result.get("ok"):
            return {"ok": False, "steps": steps, "message": install_result.get("message")}

    if not get_status(model=name)["running"]:
        start_result = start_ollama()
        steps.append({"step": "start", **start_result})
        if not start_result.get("ok"):
            return {"ok": False, "steps": steps, "message": start_result.get("message")}

    if not get_status(model=name)["model_ready"]:
        pull_result = pull_model(name)
        steps.append({"step": "pull", **pull_result})
        if not pull_result.get("ok"):
            return {"ok": False, "steps": steps, "message": pull_result.get("message")}

    final = get_status(model=name)
    return {
        "ok": final["model_ready"],
        "steps": steps,
        "status": final,
        "message": final["message"],
    }
