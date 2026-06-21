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


@ollama.command("stop")
def ollama_stop_cmd() -> None:
    """Stop the local Ollama server."""
    from backend.ollama import service as ollama_service

    result = ollama_service.stop_ollama()
    click.echo(result.get("message", "Done"))
    if not result.get("ok"):
        raise SystemExit(1)


@main.command()
@click.option("--data-dir", type=click.Path(path_type=Path), default=None)
@click.option("--host", default=None, help="Bind host (overrides config).")
@click.option("--port", default=None, type=int, help="Bind port (overrides config).")
@click.option(
    "--with-ollama/--no-ollama",
    default=None,
    help="Start local Ollama (default: on when default AI provider is ollama).",
)
@click.option("--model", default=None, help="Ollama model name for readiness checks.")
@click.option(
    "--with-frontend/--no-frontend",
    default=True,
    help="Start Vite dev server for hot-reload UI (default: on).",
)
@click.option("--frontend-port", default=None, type=int, help="Vite dev port (default: 5173).")
def up(
    data_dir: Path | None,
    host: str | None,
    port: int | None,
    with_ollama: bool | None,
    model: str | None,
    with_frontend: bool,
    frontend_port: int | None,
) -> None:
    """Start Alfred (background), Vite dev UI, and optionally Ollama."""
    from backend.runtime.supervisor import DEFAULT_FRONTEND_PORT, start_all

    manager = ConfigManager(data_dir)
    if not manager.is_initialized():
        click.echo("Alfred not initialized. Run: alfred init")
        raise SystemExit(1)
    config, _ = manager.load_merged()
    bind_host = host or config.server.host
    bind_port = port or config.server.port
    fe_port = frontend_port or int(os.environ.get("ALFRED_FRONTEND_PORT", DEFAULT_FRONTEND_PORT))
    start_ollama = (
        with_ollama
        if with_ollama is not None
        else config.ai.default_provider == "ollama"
    )

    ollama_cfg = config.ai.providers.get("ollama")
    model_name = model or (ollama_cfg.model if ollama_cfg else None)

    result = start_all(
        manager,
        host=bind_host,
        port=bind_port,
        with_ollama=start_ollama,
        with_frontend=with_frontend,
        frontend_port=fe_port,
        model=model_name,
    )
    for step in result.get("steps", []):
        click.echo(f"  • {step}")
    click.echo(result.get("message", ""))
    if result.get("frontend_url"):
        click.echo(f"Dev UI:   {result['frontend_url']}  (hot reload)")
        click.echo(f"API:      {result.get('api_url')}")
    elif result.get("url"):
        click.echo(f"Admin UI: {result['url']}")
    if result.get("log_file"):
        click.echo(f"Logs:     {result['log_file']}")
    if result.get("frontend_stdout_log"):
        click.echo(f"Vite log: {result['frontend_stdout_log']}")
    click.echo("Stop everything: alfred stop")
    if not result.get("ok"):
        raise SystemExit(1)


@main.command("stop")
@click.option("--data-dir", type=click.Path(path_type=Path), default=None)
@click.option(
    "--with-ollama/--keep-ollama",
    default=True,
    help="Also stop Ollama (default: yes).",
)
@click.option(
    "--with-frontend/--keep-frontend",
    default=True,
    help="Also stop Vite dev server (default: yes).",
)
def stop_cmd(data_dir: Path | None, with_ollama: bool, with_frontend: bool) -> None:
    """Stop Alfred, Vite dev UI, and optionally Ollama."""
    from backend.runtime.supervisor import stop_all

    manager = ConfigManager(data_dir)
    result = stop_all(manager, with_ollama=with_ollama, with_frontend=with_frontend)
    for step in result.get("steps", []):
        click.echo(f"  • {step}")
    click.echo(result.get("message", ""))
    if not result.get("ok"):
        raise SystemExit(1)


@main.group()
def slack() -> None:
    """Slack workspace utilities."""


@slack.command("emojis")
@click.option("--data-dir", type=click.Path(path_type=Path), default=None)
@click.option("--search", "-q", default=None, help="Filter emoji names (case-insensitive).")
@click.option(
    "--aliases/--no-aliases",
    default=False,
    help="Include emoji aliases (default: custom emoji only).",
)
@click.option(
    "--yaml",
    "as_yaml",
    is_flag=True,
    help="Print a ready-to-paste slack.loading_messages YAML snippet.",
)
def slack_emojis(
    data_dir: Path | None,
    search: str | None,
    aliases: bool,
    as_yaml: bool,
) -> None:
    """List custom Slack emoji shortcodes for thinking-status lines."""
    from backend.slack.emojis import (
        example_loading_line,
        fetch_workspace_emojis,
        filter_workspace_emojis,
        format_emojis_yaml,
        slack_bot_client,
    )

    manager = ConfigManager(data_dir)
    if not manager.is_initialized():
        click.echo("Alfred not initialized. Run: alfred init")
        raise SystemExit(1)

    config, _ = manager.load_merged()
    token = (config.slack.bot_token or "").strip()
    if not token.startswith("xoxb-"):
        click.echo("Slack bot token (xoxb-) not configured. Add it in the admin UI Secrets panel.")
        raise SystemExit(1)

    try:
        emojis = fetch_workspace_emojis(slack_bot_client(token))
    except RuntimeError as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(1) from exc
    except Exception as exc:
        click.echo(f"Failed to list Slack emojis: {exc}", err=True)
        raise SystemExit(1) from exc

    matches = filter_workspace_emojis(
        emojis,
        search=search,
        include_aliases=aliases,
        custom_only=not aliases,
    )
    if not matches:
        if search:
            click.echo(f"No emojis matching {search!r}.")
        else:
            click.echo("No custom workspace emojis found.")
        raise SystemExit(0)

    if as_yaml:
        click.echo(format_emojis_yaml(matches))
    else:
        for item in matches:
            if item.kind == "alias" and item.target_shortcode:
                click.echo(f"{item.shortcode}  ->  {item.target_shortcode}")
            else:
                click.echo(item.shortcode)

    custom_count = sum(1 for item in emojis if item.kind == "custom")
    click.echo("", err=True)
    click.echo(
        f"{len(matches)} shown · {custom_count} custom emoji(s) in workspace",
        err=True,
    )
    if not as_yaml:
        click.echo("Add to .alfred/config.yaml under slack.loading_messages, e.g.:", err=True)
        click.echo(f'  - "{example_loading_line(matches[0].name)}"', err=True)
        click.echo("Or run: alfred slack emojis --yaml", err=True)


@main.group()
def git() -> None:
    """Manage local repository mirrors."""


@git.command("sync")
@click.option("--data-dir", type=click.Path(path_type=Path), default=None)
def git_sync(data_dir: Path | None) -> None:
    """Clone/update shared repo mirrors (seeds per-session workspaces)."""
    from backend.git.mirror import WorkspaceMirrorManager
    from backend.paths import get_data_dir

    manager = ConfigManager(data_dir)
    if not manager.is_initialized():
        click.echo("Alfred not initialized. Run: alfred init")
        raise SystemExit(1)
    config, _ = manager.load_merged()
    if not config.git.enabled:
        click.echo("Git integration is disabled.")
        raise SystemExit(1)
    mirror = WorkspaceMirrorManager(config.git, get_data_dir(manager.data_dir))
    results = mirror.sync_shared()
    for item in results:
        if item.get("ok"):
            click.echo(f"  • {item['repo']}: {item.get('action', 'ok')}")
        else:
            click.echo(f"  • {item['repo']}: ERROR {item.get('error')}")
    if not all(item.get("ok") for item in results):
        raise SystemExit(1)

    from backend.api.routes.repo_context import build_context_after_sync

    ctx = build_context_after_sync(manager, sync_results=results)
    if ctx and ctx.get("ok"):
        click.echo(f"  • context: regenerated for {ctx.get('manifest', {}).get('repo', 'main repo')}")
    elif ctx and not ctx.get("ok"):
        click.echo(f"  • context: WARNING {ctx.get('error')}")


@git.command("workspaces")
@click.option("--data-dir", type=click.Path(path_type=Path), default=None)
def git_workspaces(data_dir: Path | None) -> None:
    """List active per-conversation mirror workspaces."""
    from backend.git.mirror import WorkspaceMirrorManager
    from backend.paths import get_data_dir

    manager = ConfigManager(data_dir)
    config, _ = manager.load_merged()
    mirror = WorkspaceMirrorManager(config.git, get_data_dir(manager.data_dir))
    rows = mirror.list_workspaces()
    if not rows:
        click.echo("No mirror workspaces.")
        return
    for row in rows:
        repos = ", ".join(row.get("repos") or []) or "(none)"
        click.echo(f"{row.get('id')}: {row.get('session_key')} — repos: {repos}")


@git.command("cleanup")
@click.option("--data-dir", type=click.Path(path_type=Path), default=None)
def git_cleanup(data_dir: Path | None) -> None:
    """Remove expired mirror workspaces (TTL / LRU)."""
    from backend.git.mirror import WorkspaceMirrorManager
    from backend.paths import get_data_dir

    manager = ConfigManager(data_dir)
    config, _ = manager.load_merged()
    mirror = WorkspaceMirrorManager(config.git, get_data_dir(manager.data_dir))
    removed = mirror.cleanup_expired()
    if removed:
        click.echo(f"Removed {len(removed)} workspace(s): {', '.join(removed)}")
    else:
        click.echo("No workspaces to remove.")


@main.group()
def context() -> None:
    """Manage generated main-repo context (.alfred/context/)."""


@context.command("generate")
@click.option("--data-dir", type=click.Path(path_type=Path), default=None)
def context_generate(data_dir: Path | None) -> None:
    """Regenerate markdown context from the shared main-repo mirror."""
    from backend.context.generator import generate_repo_context, resolve_main_repo
    from backend.paths import get_data_dir

    manager = ConfigManager(data_dir)
    if not manager.is_initialized():
        click.echo("Alfred not initialized. Run: alfred init")
        raise SystemExit(1)
    config, _ = manager.load_merged()
    if not config.git.enabled:
        click.echo("Git integration is disabled.")
        raise SystemExit(1)
    main = resolve_main_repo(config.git)
    if not main:
        click.echo("Set git.main_repo in config first.")
        raise SystemExit(1)
    try:
        manifest = generate_repo_context(get_data_dir(manager.data_dir), config.git, repo=main, ai=config.ai)
    except FileNotFoundError as exc:
        click.echo(str(exc))
        raise SystemExit(1) from exc
    click.echo(f"Generated context for {manifest.get('repo')} at commit {manifest.get('head_sha', '?')[:12]}")


@main.command("down")
@click.option("--data-dir", type=click.Path(path_type=Path), default=None)
@click.option("--with-ollama/--keep-ollama", default=True)
@click.option("--with-frontend/--keep-frontend", default=True)
def down_cmd(data_dir: Path | None, with_ollama: bool, with_frontend: bool) -> None:
    """Alias for `alfred stop`."""
    ctx = click.get_current_context()
    ctx.invoke(
        stop_cmd,
        data_dir=data_dir,
        with_ollama=with_ollama,
        with_frontend=with_frontend,
    )
