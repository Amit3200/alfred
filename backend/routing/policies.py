"""Policy layer — capability bundles and playbook tool resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.routing.capabilities import bundle_tools, load_capability_bundles, resolve_bundle_for_tools
from backend.routing.playbooks import Playbook


def resolve_playbook_allowed_tools(
    playbook: Playbook,
    *,
    data_dir: Path | None = None,
) -> list[str]:
    """Merge explicit allowlist with capability bundle tools."""
    explicit = list(playbook.allowed_tools or [])
    if explicit:
        return explicit
    if playbook.capability_bundle:
        return bundle_tools(playbook.capability_bundle, data_dir=data_dir)
    return []


def effective_output_format(playbook: Playbook, *, data_dir: Path | None = None) -> str:
    if playbook.output_format:
        return playbook.output_format
    if playbook.capability_bundle:
        bundle = load_capability_bundles(data_dir).get(playbook.capability_bundle)
        if bundle and bundle.output_format:
            return bundle.output_format
    return ""


def policy_for_tools(tool_names: list[str], *, data_dir: Path | None = None) -> str:
    """Best policy/skill name for a tool list via capability bundles."""
    bundle_name = resolve_bundle_for_tools(tool_names, data_dir=data_dir)
    if not bundle_name:
        return ""
    bundle = load_capability_bundles(data_dir).get(bundle_name)
    return bundle.policy_name if bundle else ""


def enrich_playbook_from_policy(playbook: Playbook, *, data_dir: Path | None = None) -> dict[str, Any]:
    """Summary for routing debugger / admin API."""
    tools = resolve_playbook_allowed_tools(playbook, data_dir=data_dir)
    return {
        "name": playbook.name,
        "type": playbook.playbook_type,
        "mode": playbook.mode,
        "capability_bundle": playbook.capability_bundle,
        "allowed_tools": tools,
        "output_format": effective_output_format(playbook, data_dir=data_dir),
    }
