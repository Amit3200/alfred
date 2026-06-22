"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.__version__ import __version__
from backend.api.deps import require_admin
from backend.api.routes import auth as auth_routes
from backend.api.routes import chat as chat_routes
from backend.api.routes import config as config_routes
from backend.api.routes import github as github_routes
from backend.api.routes import google as google_routes
from backend.api.routes import git_mirrors as git_mirrors_routes
from backend.api.routes import health as health_routes
from backend.api.routes import observability as observability_routes
from backend.api.routes import ollama as ollama_routes
from backend.api.routes import playbooks as playbooks_routes
from backend.api.routes import repo_context as repo_context_routes
from backend.api.routes import storage as storage_routes
from backend.config_manager import ConfigManager
from backend.logging_config import setup_logging
from backend.paths import bundled_web_dist
from backend.slack.listener import SlackSocketRunner

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    manager: ConfigManager = app.state.config_manager
    slack_runner = SlackSocketRunner(manager)
    app.state.slack_runner = slack_runner
    ok, message = slack_runner.start()
    if ok:
        logger.info("Slack ingress: %s", message)
    else:
        logger.info("Slack ingress not started: %s", message)

    try:
        config, _ = manager.load_merged()
        if config.git.enabled:
            from backend.git.mirror import WorkspaceMirrorManager

            removed = WorkspaceMirrorManager(config.git, manager.data_dir).cleanup_expired()
            if removed:
                logger.info("Cleaned up %d expired repo mirror workspace(s)", len(removed))
    except Exception:
        logger.exception("Mirror workspace cleanup failed")

    yield
    slack_runner.stop()


def create_app(data_dir: Path | None = None) -> FastAPI:
    manager = ConfigManager(data_dir)
    log_file = setup_logging(manager.data_dir)
    logger.info("Alfred log file: %s", log_file)
    app = FastAPI(
        title="Alfred",
        description="Distributable DevOps agent",
        version=__version__,
        lifespan=_lifespan,
    )
    app.state.config_manager = manager

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from fastapi import Depends
    
    app.include_router(auth_routes.router, prefix="/api")
    app.include_router(health_routes.router, prefix="/api")
    app.include_router(github_routes.router, prefix="/api")
    app.include_router(google_routes.public_router, prefix="/api")
    app.include_router(config_routes.router, prefix="/api", dependencies=[Depends(require_admin)])
    app.include_router(google_routes.admin_router, prefix="/api", dependencies=[Depends(require_admin)])
    app.include_router(ollama_routes.router, prefix="/api", dependencies=[Depends(require_admin)])
    app.include_router(chat_routes.router, prefix="/api", dependencies=[Depends(require_admin)])
    app.include_router(git_mirrors_routes.router, prefix="/api", dependencies=[Depends(require_admin)])
    app.include_router(repo_context_routes.router, prefix="/api", dependencies=[Depends(require_admin)])
    app.include_router(observability_routes.router, prefix="/api", dependencies=[Depends(require_admin)])
    app.include_router(storage_routes.router, prefix="/api", dependencies=[Depends(require_admin)])
    app.include_router(playbooks_routes.router, prefix="/api", dependencies=[Depends(require_admin)])

    static_dir = bundled_web_dist()
    if static_dir:
        assets_dir = static_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/")
        async def admin_index() -> FileResponse:
            return FileResponse(static_dir / "index.html")

        @app.get("/{full_path:path}")
        async def admin_spa(full_path: str) -> FileResponse:
            candidate = static_dir / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(static_dir / "index.html")

    return app


def build_app() -> FastAPI:
    """Uvicorn factory entrypoint (uses ALFRED_DATA_DIR when set)."""
    return create_app()
