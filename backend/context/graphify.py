"""Graphify integration — extract on sync, query for investigation."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

from backend.context.generator import read_context_manifest, resolve_main_repo, shared_mirror_path
from backend.git.api import resolve_repo_slug
from backend.models.config import AIConfig, AIProviderConfig, GitConfig
from backend.paths import repo_context_dir

logger = logging.getLogger(__name__)

GRAPHIFY_OUT = "graphify-out"
GRAPH_JSON = "graph.json"
GRAPH_REPORT = "GRAPH_REPORT.md"
DEFAULT_QUERY_TIMEOUT = 120
DEFAULT_EXTRACT_TIMEOUT_MINUTES = 120
MAX_EXTRACT_TIMEOUT_MINUTES = 360
GRAPHIFY_INSTALL_HINT = 'Install with: uv sync --extra graphify  (or: pip install "graphifyy>=0.5.0")'
MAX_REPORT_CHARS = 120_000
MAX_SUMMARY_NODES = 25
GRAPHIFY_LOCK_NAME = "graphify.extract.lock"


class GraphifyExtractBusy(Exception):
    """Another Graphify extract is already running for this repo."""

    def __init__(self, pid: int | None = None, started_at: str | None = None) -> None:
        self.pid = pid
        self.started_at = started_at
        detail = f" (pid {pid})" if pid else ""
        super().__init__(f"Graphify extract already running{detail}")

_GRAPHIFY_BACKEND = {
    "kimi": "kimi",
    "anthropic": "claude",
    "openai": "openai",
    "gemini": "gemini",
    "ollama": "ollama",
}

_CLOUD_PROVIDERS = frozenset(_GRAPHIFY_BACKEND) - {"ollama"}

_ENV_KEY_FALLBACKS: dict[str, list[str]] = {
    "kimi": ["MOONSHOT_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
}


def _graphify_lock_path(data_dir: Path, repo_slug: str) -> Path:
    return repo_context_dir(data_dir, repo_slug) / GRAPHIFY_LOCK_NAME


def _parse_lock_file(text: str) -> tuple[int | None, str | None]:
    line = text.strip().splitlines()[0] if text.strip() else ""
    if not line:
        return None, None
    parts = line.split(maxsplit=1)
    try:
        pid = int(parts[0])
    except ValueError:
        return None, parts[0] if parts else None
    started_at = parts[1] if len(parts) > 1 else None
    return pid, started_at


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def graphify_extract_status(data_dir: Path, repo_slug: str) -> dict[str, Any]:
    """Return whether an extract lock is held for this repo."""
    path = _graphify_lock_path(data_dir, repo_slug)
    if not path.is_file():
        return {"running": False}
    try:
        pid, started_at = _parse_lock_file(path.read_text(encoding="utf-8"))
    except OSError:
        return {"running": False}
    if pid and not _pid_running(pid):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return {"running": False, "stale_lock": True}
    return {
        "running": True,
        "pid": pid,
        "started_at": started_at,
        "lock_path": str(path),
    }


@contextmanager
def graphify_extract_lock(data_dir: Path, repo_slug: str) -> Iterator[None]:
    """Cross-process lock — one Graphify extract per repo at a time."""
    if fcntl is None:
        yield
        return

    path = _graphify_lock_path(data_dir, repo_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.seek(0)
            pid, started_at = _parse_lock_file(handle.read())
            raise GraphifyExtractBusy(pid, started_at) from None
        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()} {_now_iso()}\n")
        handle.flush()
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _extract_timeout_seconds(git: GitConfig) -> int:
    minutes = git.graphify_extract_timeout_minutes or DEFAULT_EXTRACT_TIMEOUT_MINUTES
    minutes = max(15, min(int(minutes), MAX_EXTRACT_TIMEOUT_MINUTES))
    return minutes * 60


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _rel_data_path(data_dir: Path, path: Path | None) -> str | None:
    if not path:
        return None
    try:
        return str(path.relative_to(data_dir))
    except ValueError:
        return str(path)


def _file_size(path: Path | None) -> int | None:
    if not path or not path.is_file():
        return None
    try:
        return path.stat().st_size
    except OSError:
        return None


def _graphify_manifest_meta(data_dir: Path, repo_slug: str) -> dict[str, Any]:
    manifest = read_context_manifest(data_dir, repo_slug) or {}
    meta = manifest.get("graphify")
    return meta if isinstance(meta, dict) else {}


def _read_graph_payload(graph_path: Path | None) -> dict[str, Any] | None:
    if not graph_path:
        return None
    try:
        payload = json.loads(graph_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _node_label(node: Any) -> str:
    if not isinstance(node, dict):
        return str(node)
    for key in ("label", "name", "id", "path"):
        value = node.get(key)
        if value:
            return str(value)
    return "?"


def _node_kind(node: Any) -> str:
    if not isinstance(node, dict):
        return "unknown"
    for key in ("kind", "type", "node_type"):
        value = node.get(key)
        if value:
            return str(value)
    return "unknown"


def _edge_endpoints(edge: Any) -> tuple[str | None, str | None]:
    if not isinstance(edge, dict):
        return None, None
    source = edge.get("source") or edge.get("from") or edge.get("src")
    target = edge.get("target") or edge.get("to") or edge.get("dst")
    return (
        str(source) if source is not None else None,
        str(target) if target is not None else None,
    )


def _provider_candidates(ai: AIConfig) -> list[str]:
    """Cloud providers with keys first; Ollama only when no cloud key is available."""
    names: list[str] = []
    for name in (ai.routing.investigation, ai.default_provider):
        if name and name != "ollama" and name not in names:
            names.append(name)
    for name in ("kimi", "anthropic", "openai", "gemini"):
        if name not in names:
            names.append(name)
    for name in (ai.routing.investigation, ai.default_provider):
        if name == "ollama" and name not in names:
            names.append(name)
    if "ollama" not in names:
        names.append("ollama")
    return names


def _try_graphify_provider(
    ai: AIConfig,
    name: str,
) -> tuple[list[str], dict[str, str], str] | None:
    cfg = ai.providers.get(name)
    if not cfg:
        return None
    backend = _GRAPHIFY_BACKEND.get(name)
    if not backend:
        return None
    api_key = _provider_api_key(name, cfg)

    if backend == "ollama":
        if _any_cloud_provider_has_key(ai):
            return None
        if not cfg.enabled:
            return None
    elif not api_key:
        return None

    args = [f"--backend={backend}"]
    if cfg.model:
        args.append(f"--model={cfg.model}")
    env = _graphify_env_for_provider(name, cfg, api_key)
    return args, env, name


def _provider_api_key(name: str, cfg: AIProviderConfig) -> str:
    if cfg.api_key.strip():
        return cfg.api_key.strip()
    for env_name in _ENV_KEY_FALLBACKS.get(name, []):
        if value := os.environ.get(env_name, "").strip():
            return value
    if name == "ollama":
        return "ollama"
    return ""


def _cloud_provider_has_key(ai: AIConfig, name: str) -> bool:
    if name not in _CLOUD_PROVIDERS:
        return False
    cfg = ai.providers.get(name)
    if not cfg:
        return False
    return bool(_provider_api_key(name, cfg))


def _any_cloud_provider_has_key(ai: AIConfig) -> bool:
    return any(_cloud_provider_has_key(ai, name) for name in _CLOUD_PROVIDERS)


def _graphify_env_for_provider(name: str, cfg: AIProviderConfig, api_key: str) -> dict[str, str]:
    env: dict[str, str] = {}
    if name == "kimi" and api_key:
        env["MOONSHOT_API_KEY"] = api_key
    elif name == "openai":
        if api_key:
            env["OPENAI_API_KEY"] = api_key
        if cfg.base_url:
            env["OPENAI_BASE_URL"] = cfg.base_url
        if cfg.model:
            env["OPENAI_MODEL"] = cfg.model
    elif name == "anthropic":
        if api_key:
            env["ANTHROPIC_API_KEY"] = api_key
        if cfg.model:
            env["ANTHROPIC_MODEL"] = cfg.model
    elif name == "gemini" and api_key:
        env["GEMINI_API_KEY"] = api_key
        env["GOOGLE_API_KEY"] = api_key
    elif name == "ollama":
        if cfg.base_url:
            env["OPENAI_BASE_URL"] = cfg.base_url
        if cfg.model:
            env["OPENAI_MODEL"] = cfg.model
    return env


def resolve_graphify_llm(
    ai: AIConfig | None,
) -> tuple[list[str], dict[str, str], str | None]:
    """Map Alfred AI config to graphify --backend flags and subprocess env."""
    if not ai:
        return [], {}, None

    for name in _provider_candidates(ai):
        if picked := _try_graphify_provider(ai, name):
            return picked

    return [], {}, None


def graphify_llm_status(ai: AIConfig | None) -> dict[str, Any]:
    args, env, provider = resolve_graphify_llm(ai)
    return {
        "provider": provider,
        "ready": bool(provider),
        "backend": args[0].split("=", 1)[1] if args else None,
        "model": args[1].split("=", 1)[1] if len(args) > 1 else None,
        "uses_env": sorted(env.keys()),
    }


def resolve_graphify_command() -> list[str] | None:
    """Return argv prefix to invoke graphify — venv script, PATH, or python -m."""
    if path := shutil.which("graphify"):
        return [path]

    venv_bin = Path(sys.executable).resolve().parent / "graphify"
    if venv_bin.is_file() and os_access_executable(venv_bin):
        return [str(venv_bin)]

    for module in ("graphify", "graphifyy"):
        if python_module_available(module):
            return [sys.executable, "-m", module]

    return None


def os_access_executable(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_mode & 0o111
    except OSError:
        return False


def python_module_available(module: str) -> bool:
    try:
        proc = subprocess.run(
            [sys.executable, "-m", module, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def graphify_cli_available() -> bool:
    return resolve_graphify_command() is not None


def graphify_version() -> str | None:
    base = resolve_graphify_command()
    if not base:
        return None
    try:
        proc = subprocess.run(
            [*base, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0:
            return None
        return (proc.stdout or proc.stderr or "").strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def graphify_out_dir(data_dir: Path, repo_slug: str) -> Path:
    path = repo_context_dir(data_dir, repo_slug) / GRAPHIFY_OUT
    path.mkdir(parents=True, exist_ok=True)
    return path


def graph_json_path(data_dir: Path, repo_slug: str) -> Path | None:
    path = graphify_out_dir(data_dir, repo_slug) / GRAPH_JSON
    return path if path.is_file() else None


def graph_report_path(data_dir: Path, repo_slug: str) -> Path | None:
    path = graphify_out_dir(data_dir, repo_slug) / GRAPH_REPORT
    return path if path.is_file() else None


def graph_status(data_dir: Path, git: GitConfig, *, ai: AIConfig | None = None) -> dict[str, Any]:
    slug = resolve_main_repo(git)
    available = graphify_cli_available()
    version = graphify_version() if available else None
    llm = graphify_llm_status(ai)
    extract = graphify_extract_status(data_dir, slug) if slug else {"running": False}
    base = {
        "available": available,
        "enabled": git.graphify_enabled,
        "version": version,
        "install_hint": None if available else GRAPHIFY_INSTALL_HINT,
        "llm_provider": llm.get("provider"),
        "llm_ready": llm.get("ready"),
        "llm_backend": llm.get("backend"),
        "llm_model": llm.get("model"),
        "extract_running": extract.get("running"),
        "extract_pid": extract.get("pid"),
        "extract_started_at": extract.get("started_at"),
        "extract_timeout_minutes": git.graphify_extract_timeout_minutes
        or DEFAULT_EXTRACT_TIMEOUT_MINUTES,
    }
    if not slug:
        return {
            **base,
            "repo": "",
            "present": False,
            "node_count": None,
            "edge_count": None,
            "report_present": False,
            "graph_rel_path": None,
            "report_rel_path": None,
            "out_rel_path": None,
            "graph_bytes": None,
            "report_bytes": None,
            "built_at": None,
            "last_error": None,
            "mirror_present": False,
        }

    graph_path = graph_json_path(data_dir, slug)
    report = graph_report_path(data_dir, slug)
    payload = _read_graph_payload(graph_path)
    node_count = edge_count = None
    if payload:
        nodes = payload.get("nodes")
        edges = payload.get("edges")
        if isinstance(nodes, list):
            node_count = len(nodes)
        if isinstance(edges, list):
            edge_count = len(edges)

    meta = _graphify_manifest_meta(data_dir, slug)
    last_ok = meta.get("ok") is True
    built_at = meta.get("rebuilt_at") or (meta.get("generated_at") if last_ok else None)
    if graph_path is not None and built_at is None:
        try:
            built_at = datetime.fromtimestamp(
                graph_path.stat().st_mtime,
                tz=timezone.utc,
            ).isoformat()
        except OSError:
            pass
    if graph_path is not None and node_count:
        last_error = None
    elif last_ok:
        last_error = None
    else:
        last_error = meta.get("error") or meta.get("last_error")

    return {
        **base,
        "repo": slug,
        "present": graph_path is not None,
        "node_count": node_count,
        "edge_count": edge_count,
        "report_present": report is not None,
        "graph_path": str(graph_path) if graph_path else None,
        "graph_rel_path": _rel_data_path(data_dir, graph_path),
        "report_path": str(report) if report else None,
        "report_rel_path": _rel_data_path(data_dir, report),
        "out_rel_path": _rel_data_path(data_dir, graphify_out_dir(data_dir, slug)),
        "graph_bytes": _file_size(graph_path),
        "report_bytes": _file_size(report),
        "built_at": built_at,
        "last_error": last_error,
        "mirror_present": shared_mirror_path(data_dir, slug).is_dir()
        and any(shared_mirror_path(data_dir, slug).iterdir()),
    }


def graph_summary(data_dir: Path, repo_slug: str, *, limit: int = MAX_SUMMARY_NODES) -> dict[str, Any]:
    """Lightweight graph stats for admin UI."""
    graph_path = graph_json_path(data_dir, repo_slug)
    payload = _read_graph_payload(graph_path)
    if not payload:
        return {
            "present": False,
            "node_count": 0,
            "edge_count": 0,
            "node_kinds": {},
            "top_nodes": [],
            "sample_edges": [],
        }

    nodes = payload.get("nodes") if isinstance(payload.get("nodes"), list) else []
    edges = payload.get("edges") if isinstance(payload.get("edges"), list) else []
    labels: dict[str, str] = {}
    kinds: Counter[str] = Counter()
    degrees: Counter[str] = Counter()

    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or node.get("name") or "")
        if not node_id:
            continue
        labels[node_id] = _node_label(node)
        kinds[_node_kind(node)] += 1

    sample_edges: list[dict[str, str]] = []
    for edge in edges:
        source, target = _edge_endpoints(edge)
        if source:
            degrees[source] += 1
        if target:
            degrees[target] += 1
        if len(sample_edges) < 8 and source and target:
            sample_edges.append(
                {
                    "source": labels.get(source, source),
                    "target": labels.get(target, target),
                    "kind": str(edge.get("kind") or edge.get("type") or "edge"),
                }
            )

    top_nodes = []
    for node_id, degree in degrees.most_common(max(1, min(limit, MAX_SUMMARY_NODES))):
        top_nodes.append(
            {
                "id": node_id,
                "label": labels.get(node_id, node_id),
                "degree": degree,
            }
        )

    return {
        "present": True,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_kinds": dict(kinds.most_common(12)),
        "top_nodes": top_nodes,
        "sample_edges": sample_edges,
    }


def graph_detail(data_dir: Path, git: GitConfig, *, ai: AIConfig | None = None) -> dict[str, Any]:
    """Full Graphify status payload for admin UI."""
    status = graph_status(data_dir, git, ai=ai)
    slug = status.get("repo")
    summary = graph_summary(data_dir, slug) if slug and status.get("present") else None
    return {**status, "summary": summary}


def _format_graph_summary_report(slug: str, summary: dict[str, Any]) -> str:
    """Markdown overview when GRAPH_REPORT.md was not generated (--no-cluster extract)."""
    lines = [
        f"# Graph summary — {slug}",
        "",
        "Fast extract skips Graphify clustering, so `GRAPH_REPORT.md` was not created.",
        "Use **View graph stats** for the interactive breakdown, or `graphify query` for questions.",
        "",
        f"- **Nodes:** {summary.get('node_count', 0):,}",
        f"- **Edges:** {summary.get('edge_count', 0):,}",
        "",
    ]
    kinds = summary.get("node_kinds") or {}
    if kinds:
        lines.append("## Node kinds")
        lines.append("")
        for kind, count in kinds.items():
            lines.append(f"- `{kind}`: {count:,}")
        lines.append("")

    top_nodes = summary.get("top_nodes") or []
    if top_nodes:
        lines.append("## Most connected nodes")
        lines.append("")
        for node in top_nodes[:15]:
            label = node.get("label") or node.get("id") or "?"
            degree = node.get("degree", 0)
            lines.append(f"- **{label}** ({degree:,} connections)")
        lines.append("")

    sample_edges = summary.get("sample_edges") or []
    if sample_edges:
        lines.append("## Sample edges")
        lines.append("")
        for edge in sample_edges[:8]:
            source = edge.get("source") or "?"
            target = edge.get("target") or "?"
            kind = edge.get("kind") or "edge"
            lines.append(f"- `{source}` → `{target}` ({kind})")

    return "\n".join(lines).strip() + "\n"


def load_graph_report(
    data_dir: Path,
    git: GitConfig,
    *,
    max_chars: int = MAX_REPORT_CHARS,
) -> dict[str, Any]:
    slug = resolve_main_repo(git)
    if not slug:
        return {"present": False, "content": "", "repo": ""}

    report = graph_report_path(data_dir, slug)
    if report:
        text = report.read_text(encoding="utf-8", errors="replace")
        truncated = len(text) > max_chars
        if truncated:
            text = text[: max_chars - 20].rstrip() + "\n\n...(truncated)"
        return {
            "present": True,
            "repo": slug,
            "content": text,
            "truncated": truncated,
            "bytes": _file_size(report),
            "rel_path": _rel_data_path(data_dir, report),
            "synthetic": False,
        }

    summary = graph_summary(data_dir, slug)
    if not summary.get("present"):
        return {"present": False, "content": "", "repo": slug}

    text = _format_graph_summary_report(slug, summary)
    truncated = len(text) > max_chars
    if truncated:
        text = text[: max_chars - 20].rstrip() + "\n\n...(truncated)"
    graph_path = graph_json_path(data_dir, slug)
    return {
        "present": True,
        "repo": slug,
        "content": text,
        "truncated": truncated,
        "bytes": len(text.encode("utf-8")),
        "rel_path": _rel_data_path(data_dir, graph_path),
        "synthetic": True,
    }


def record_graphify_build(
    data_dir: Path,
    repo_slug: str,
    result: dict[str, Any],
) -> None:
    """Persist latest Graphify build metadata into context manifest."""
    from backend.context.generator import MANIFEST_NAME

    manifest = read_context_manifest(data_dir, repo_slug) or {}
    meta = {**result, "rebuilt_at": _now_iso()}
    if meta.get("ok"):
        meta.pop("error", None)
        meta.pop("last_error", None)
    manifest["graphify"] = meta
    out_dir = repo_context_dir(data_dir, repo_slug)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _run_graphify(
    args: list[str],
    *,
    timeout: int,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    base = resolve_graphify_command()
    if not base:
        raise FileNotFoundError(GRAPHIFY_INSTALL_HINT)
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    return subprocess.run(
        [*base, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=run_env,
    )


def extract_graph(
    data_dir: Path,
    git: GitConfig,
    *,
    repo: str | None = None,
    ai: AIConfig | None = None,
) -> dict[str, Any]:
    """Run graphify extract on the shared mirror (AST-only flags when possible)."""
    if not git.graphify_enabled:
        return {"ok": False, "skipped": True, "reason": "graphify_enabled is false"}

    if not graphify_cli_available():
        return {"ok": False, "error": GRAPHIFY_INSTALL_HINT}

    slug = resolve_repo_slug(repo or git.main_repo or "", git) if (repo or git.main_repo) else None
    if not slug:
        return {"ok": False, "error": "main_repo is not configured"}

    mirror = shared_mirror_path(data_dir, slug)
    if not mirror.is_dir() or not any(mirror.iterdir()):
        return {"ok": False, "error": f"Shared mirror for {slug!r} is missing"}

    llm_args, llm_env, llm_provider = resolve_graphify_llm(ai)
    if not llm_provider:
        return {
            "ok": False,
            "error": (
                "No LLM API key configured for Graphify semantic extraction. "
                "Add a key under Configure → Secrets (e.g. Kimi) or set MOONSHOT_API_KEY."
            ),
        }

    out_dir = graphify_out_dir(data_dir, slug)
    timeout_seconds = _extract_timeout_seconds(git)
    timeout_minutes = timeout_seconds // 60
    try:
        with graphify_extract_lock(data_dir, slug):
            logger.info(
                "Graphify extract starting for %s via %s (timeout=%sm, %s)",
                slug,
                llm_provider,
                timeout_minutes,
                " ".join(llm_args),
            )
            proc = _run_graphify(
                [
                    "extract",
                    str(mirror),
                    "--no-viz",
                    "--no-cluster",
                    "--force",
                    "--api-timeout",
                    "900",
                    *llm_args,
                ],
                timeout=timeout_seconds,
                env=llm_env,
            )
    except GraphifyExtractBusy as exc:
        return {
            "ok": False,
            "error": str(exc),
            "busy": True,
            "extract_pid": exc.pid,
            "extract_started_at": exc.started_at,
            "llm_provider": llm_provider,
        }
    except subprocess.TimeoutExpired:
        msg = (
            f"graphify extract timed out after {timeout_minutes} minutes. "
            "Repos with many doc/image files can take longer on Kimi — "
            "wait and retry once, or raise git.graphify_extract_timeout_minutes (max 360)."
        )
        logger.warning("Graphify extract timed out for %s after %s minutes", slug, timeout_minutes)
        return {"ok": False, "error": msg, "timed_out": True, "timeout_minutes": timeout_minutes}
    except FileNotFoundError as exc:
        return {"ok": False, "error": str(exc)}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "graphify extract failed").strip()
        logger.warning("graphify extract failed for %s: %s", slug, err[:500])
        return {"ok": False, "error": err[:2000], "llm_provider": llm_provider}

    _relocate_graphify_output(mirror, out_dir)
    status = graph_status(data_dir, git, ai=ai)
    logger.info(
        "Graphify extract complete for %s via %s (nodes=%s edges=%s)",
        slug,
        llm_provider,
        status.get("node_count"),
        status.get("edge_count"),
    )
    return {"ok": True, "repo": slug, "llm_provider": llm_provider, **status}


def query_graph(
    data_dir: Path,
    git: GitConfig,
    question: str,
    *,
    repo: str | None = None,
    budget: int | None = None,
) -> dict[str, Any]:
    """Run graphify query against the stored graph."""
    slug = resolve_main_repo(git)
    if repo:
        try:
            slug = resolve_repo_slug(repo, git)
        except ValueError:
            slug = repo.strip()

    if not slug:
        return {"ok": False, "error": "main_repo is not configured"}

    graph_path = graph_json_path(data_dir, slug)
    if not graph_path:
        return {
            "ok": False,
            "error": f"No Graphify graph for {slug}. Enable graphify and sync main repo.",
        }

    if not graphify_cli_available():
        report = graph_report_path(data_dir, slug)
        if report:
            excerpt = report.read_text(encoding="utf-8", errors="replace")[:4000]
            return {
                "ok": True,
                "repo": slug,
                "question": question,
                "answer": excerpt,
                "source": "GRAPH_REPORT.md",
            }
        return {"ok": False, "error": f"graphify not installed — {GRAPHIFY_INSTALL_HINT}"}

    args = ["query", question, "--graph", str(graph_path)]
    if budget:
        args.extend(["--dfs", "--budget", str(max(100, min(budget, 5000)))])

    try:
        proc = _run_graphify(args, timeout=DEFAULT_QUERY_TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "graphify query timed out"}
    except FileNotFoundError as exc:
        return {"ok": False, "error": str(exc)}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "graphify query failed").strip()
        return {"ok": False, "error": err[:2000]}

    answer = (proc.stdout or "").strip()
    if not answer and proc.stderr:
        answer = proc.stderr.strip()
    return {
        "ok": True,
        "repo": slug,
        "question": question,
        "answer": answer or "(empty response)",
        "source": "graphify query",
    }


def load_graph_report_excerpt(
    data_dir: Path,
    git: GitConfig,
    *,
    max_chars: int = 2000,
) -> str:
    slug = resolve_main_repo(git)
    if not slug:
        return ""
    report = graph_report_path(data_dir, slug)
    if not report:
        return ""
    text = report.read_text(encoding="utf-8", errors="replace").strip()
    if len(text) > max_chars:
        return text[: max_chars - 20].rstrip() + "\n\n...(truncated)"
    return text


def _relocate_graphify_output(mirror: Path, dest: Path) -> None:
    """Move graphify-out from mirror checkout into .alfred/context/ if needed."""
    candidates = [
        mirror / GRAPHIFY_OUT,
        mirror.parent / GRAPHIFY_OUT,
    ]
    for src in candidates:
        if not src.is_dir():
            continue
        if src.resolve() == dest.resolve():
            return
        dest.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            target = dest / item.name
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    target.unlink(missing_ok=True)
            shutil.move(str(item), str(target))
        shutil.rmtree(src, ignore_errors=True)
        return
