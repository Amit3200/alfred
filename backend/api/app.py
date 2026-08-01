"""FastAPI application factory."""

from __future__ import annotations
from backend.integrations.git.mirror import WorkspaceMirrorManager
from fastapi import Depends


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
from backend.api.routes import branding as branding_routes
from backend.api.routes import chat as chat_routes
from backend.api.routes import config as config_routes
from backend.api.routes import github as github_routes
from backend.api.routes import google as google_routes
from backend.api.routes import git_mirrors as git_mirrors_routes
from backend.api.routes import health as health_routes
from backend.api.routes import observability as observability_routes
from backend.api.routes import ollama as ollama_routes
from backend.api.routes import playbooks as playbooks_routes
from backend.api.routes import scripts as scripts_routes
from backend.api.routes import repo_context as repo_context_routes
from backend.api.routes import storage as storage_routes
from backend.config_manager import ConfigManager
from backend.logging_config import setup_logging
from backend.paths import bundled_web_dist
from backend.integrations.slack.listener import SlackSocketRunner
from backend.routing.playbook_store_registry import get_playbook_store

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    manager: ConfigManager = app.state.config_manager

    # Start persistent task queue and background worker
    from backend.db.sqlite_queue import SQLiteQueue
    from backend.orchestrator.worker import TaskQueueWorker
    queue = SQLiteQueue(manager.data_dir)
    worker = TaskQueueWorker(manager, queue)
    app.state.queue = queue
    app.state.queue_worker = worker
    worker.start()

    slack_runner = SlackSocketRunner(manager)
    app.state.slack_runner = slack_runner
    ok, message = slack_runner.start()
    if ok:
        logger.info("Slack ingress: %s", message)
    else:
        logger.info("Slack ingress not started: %s", message)

    from backend.runtime.scheduler import SchedulerService
    scheduler = SchedulerService(manager, queue)
    app.state.scheduler = scheduler
    scheduler.start()

    try:
        config, _ = manager.load_merged()
    except Exception:
        logger.exception("Failed to load config during startup warmup")
        config = None

    if config is not None:
        try:
            get_playbook_store(manager.data_dir, disabled_skills=config.skills.disabled)
        except Exception:
            logger.exception("Playbook store warmup failed")

        try:
            if config.git.enabled:
                removed = WorkspaceMirrorManager(config.git, manager.data_dir).cleanup_expired()
                if removed:
                    logger.info("Cleaned up %d expired repo mirror workspace(s)", len(removed))
        except Exception:
            logger.exception("Mirror workspace cleanup failed")

        try:
            if config.scripts.enabled and config.scripts.remote.repo and config.scripts.remote.sync_on_startup:
                from backend.integrations.company_scripts.sync import sync_scripts_repository

                result = sync_scripts_repository(config, manager.data_dir)
                if result.get("ok"):
                    logger.info("Scripts repo sync: %s", result.get("message"))
                elif not result.get("skipped"):
                    logger.warning("Scripts repo sync failed: %s", result.get("message"))
        except Exception:
            logger.exception("Scripts repo startup sync failed")

    yield
    slack_runner.stop()
    scheduler.stop()
    worker.stop()


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

    pass
    
    app.include_router(auth_routes.router, prefix="/api")
    app.include_router(health_routes.router, prefix="/api")
    app.include_router(branding_routes.public_router, prefix="/api")
    app.include_router(branding_routes.admin_router, prefix="/api", dependencies=[Depends(require_admin)])
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
    app.include_router(scripts_routes.router, prefix="/api", dependencies=[Depends(require_admin)])

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
