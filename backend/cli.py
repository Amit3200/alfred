"""Alfred CLI — init, serve, version."""

from __future__ import annotations

import os
from pathlib import Path

import click
import uvicorn

from backend.__version__ import __version__
from backend.api.app import create_app
from backend.config_manager import ConfigManager
from backend.paths import ENV_DATA_DIR, get_data_dir, log_path


@click.group()
@click.version_option(__version__, prog_name="alfred")
def main() -> None:
    """Alfred — distributable DevOps agent."""


@main.command()
@click.option(
    "--data-dir",
    type=click.Path(path_type=Path),
    default=None,
    help=f"Data directory (default: ~/.alfred or ${ENV_DATA_DIR})",
)
@click.option("--force", is_flag=True, help="Re-initialize even if already set up.")
def init(data_dir: Path | None, force: bool) -> None:
    """Initialize Alfred data directory and generate admin token."""
    manager = ConfigManager(data_dir)
    config = manager.init(force=force)
    _, secrets = manager.load_merged()
    click.echo(f"Alfred initialized at: {manager.data_dir}")
    click.echo(f"Admin token: {secrets.server_admin_token}")
    click.echo("Save this token — you'll need it to update secrets in the admin UI.")
    click.echo(f"Start the server: alfred serve --data-dir {manager.data_dir}")


@main.command()
@click.option("--data-dir", type=click.Path(path_type=Path), default=None)
@click.option("--host", default=None, help="Bind host (overrides config).")
@click.option("--port", default=None, type=int, help="Bind port (overrides config).")
@click.option("--reload", is_flag=True, help="Dev auto-reload.")
def serve(data_dir: Path | None, host: str | None, port: int | None, reload: bool) -> None:
    """Start Alfred API server and admin UI."""
    manager = ConfigManager(data_dir)
    if not manager.is_initialized():
        click.echo("Alfred not initialized. Run: alfred init")
        raise SystemExit(1)
    config, _ = manager.load_merged()
    bind_host = host or config.server.host
    bind_port = port or config.server.port
    click.echo(f"Alfred {__version__} serving on http://{bind_host}:{bind_port}")
    click.echo(f"Logs: {log_path(manager.data_dir)}")
    if reload:
        os.environ[ENV_DATA_DIR] = str(manager.data_dir)
        uvicorn.run(
            "backend.api.app:build_app",
            host=bind_host,
            port=bind_port,
            reload=True,
            factory=True,
        )
    else:
        app = create_app(data_dir)
        uvicorn.run(app, host=bind_host, port=bind_port)


@main.command()
@click.option("--data-dir", type=click.Path(path_type=Path), default=None)
def status(data_dir: Path | None) -> None:
    """Show initialization status and data directory."""
    manager = ConfigManager(data_dir)
    click.echo(f"Data dir: {manager.data_dir}")
    click.echo(f"Log file: {log_path(manager.data_dir)}")
    click.echo(f"Initialized: {manager.is_initialized()}")
    if manager.is_initialized():
        config, _ = manager.load_merged()
        click.echo(f"Default AI provider: {config.ai.default_provider}")
        click.echo(f"Server: {config.server.host}:{config.server.port}")
        from backend.slack.listener import slack_listener_ready

        ready, msg = slack_listener_ready(config)
        click.echo(f"Slack ingress ready: {ready} ({msg})")


@main.command("exec")
@click.argument("message")
@click.option("--data-dir", type=click.Path(path_type=Path), default=None)
def exec_cmd(message: str, data_dir: Path | None) -> None:
    """Run a message through Alfred locally (same path as Slack, without posting)."""
    from backend.ingress.processor import TaskProcessor
    from backend.ingress.render import render_for_channel
    from backend.models.task import Task

    manager = ConfigManager(data_dir)
    if not manager.is_initialized():
        click.echo("Alfred not initialized. Run: alfred init")
        raise SystemExit(1)
    config, _ = manager.load_merged()
    task = Task(
        source="cli",
        user_id="cli",
        raw_text=message,
        cleaned_intent=message.strip(),
    )
    processor = TaskProcessor(config, data_dir=manager.data_dir)
    try:
        response = processor.process(task)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc
    click.echo(render_for_channel(response, "cli"))


@main.command()
@click.option("--data-dir", type=click.Path(path_type=Path), default=None)
def token(data_dir: Path | None) -> None:
    """Print the admin token for the admin UI (from alfred init)."""
    manager = ConfigManager(data_dir)
    if not manager.is_initialized():
        click.echo("Alfred not initialized. Run: alfred init")
        raise SystemExit(1)
    _, secrets = manager.load_merged()
    if not secrets.server_admin_token:
        click.echo("No admin token found. Run: alfred init --force")
        raise SystemExit(1)
    click.echo(f"Data dir: {manager.data_dir}", err=True)
    click.echo(secrets.server_admin_token)


@main.group()
def ollama() -> None:
    """Manage local Ollama (install, start, pull models)."""


@ollama.command("status")
@click.option("--data-dir", type=click.Path(path_type=Path), default=None)
def ollama_status(data_dir: Path | None) -> None:
    """Show Ollama install and runtime status."""
    from backend.ollama import service as ollama_service

    manager = ConfigManager(data_dir)
    config, _ = manager.load_merged()
    provider = config.ai.providers.get("ollama")
    base_url = provider.base_url if provider else None
    model = provider.model if provider else None
    result = ollama_service.get_status(base_url=base_url, model=model)
    click.echo(f"Installed: {result['installed']}")
    click.echo(f"Running: {result['running']}")
    click.echo(f"Model ready ({result['recommended_model']}): {result['model_ready']}")
    click.echo(f"API: {result['api_url']}")
    if result.get("models"):
        click.echo(f"Models: {', '.join(result['models'])}")
    click.echo(result["message"])
    if result.get("install_hint") and not result["installed"]:
        click.echo(f"Install: {result['install_hint']}")


@ollama.command("install")
def ollama_install_cmd() -> None:
    """Install Ollama on this machine."""
    from backend.ollama import service as ollama_service

    result = ollama_service.install_ollama()
    click.echo(result.get("message", "Done"))
    if not result.get("ok"):
        raise SystemExit(1)


@ollama.command("start")
def ollama_start_cmd() -> None:
    """Start the local Ollama server."""
    from backend.ollama import service as ollama_service

    result = ollama_service.start_ollama()
    click.echo(result.get("message", "Done"))
    if not result.get("ok"):
        raise SystemExit(1)


@ollama.command("pull")
@click.option("--model", default=None, help="Model name (default: llama3)")
def ollama_pull_cmd(model: str | None) -> None:
    """Pull an Ollama model."""
    from backend.ollama import service as ollama_service

    result = ollama_service.pull_model(model)
    click.echo(result.get("message", "Done"))
    if not result.get("ok"):
        raise SystemExit(1)


@ollama.command("setup")
@click.option("--model", default=None, help="Model name (default: llama3)")
def ollama_setup_cmd(model: str | None) -> None:
    """Install, start, and pull the default local model."""
    from backend.ollama import service as ollama_service

    result = ollama_service.setup_local(model)
    for step in result.get("steps", []):
        click.echo(f"  [{step.get('step')}] {step.get('message', step.get('ok'))}")
    click.echo(result.get("message", "Done"))
    if not result.get("ok"):
        raise SystemExit(1)
