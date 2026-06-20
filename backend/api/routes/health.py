"""Health and status endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from backend.__version__ import __version__
from backend.health import run_all_checks

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> dict:
    manager = request.app.state.config_manager
    from backend.paths import log_path

    return {
        "status": "ok",
        "version": __version__,
        "initialized": manager.is_initialized(),
        "data_dir": str(manager.data_dir),
        "log_file": str(log_path(manager.data_dir)),
    }


@router.get("/health/checks")
def health_checks(request: Request) -> dict:
    manager = request.app.state.config_manager
    config, _ = manager.load_merged()
    checks = run_all_checks(config)
    runner = getattr(request.app.state, "slack_runner", None)
    if runner is not None:
        checks["slack_ingress"] = runner.status()
    return checks
