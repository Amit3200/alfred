"""Admin API for Alfred tool catalog."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.api.deps import require_admin
from backend.config_manager import ConfigManager
from backend.routing.playbook_store_registry import get_playbook_store
from backend.tools.list_catalog import build_tools_catalog

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("/catalog")
def get_tools_catalog(
    manager: ConfigManager = Depends(require_admin),
    domain: str | None = Query(None, description="Filter by domain, e.g. git, jira"),
    enabled_only: bool = Query(False, description="Return only enabled tools"),
) -> dict:
    config, _ = manager.load_merged()
    store = get_playbook_store(manager.data_dir)
    catalog = build_tools_catalog(config, playbooks=store.list_playbooks())

    if domain or enabled_only:
        tools = catalog.get("tools") or []
        if domain:
            tools = [t for t in tools if t.get("domain") == domain]
        if enabled_only:
            tools = [t for t in tools if t.get("enabled")]
        domain_names = sorted({t["domain"] for t in tools})
        domain_buckets: dict[str, list] = {}
        for t in tools:
            domain_buckets.setdefault(t["domain"], []).append(t)
        from backend.tools.list_catalog import _DOMAIN_LABELS

        catalog = {
            **catalog,
            "tools": tools,
            "domains": [
                {
                    "name": d,
                    "label": _DOMAIN_LABELS.get(d, d),
                    "tool_count": len(domain_buckets.get(d, [])),
                    "enabled_count": sum(1 for t in domain_buckets.get(d, []) if t.get("enabled")),
                    "tools": domain_buckets.get(d, []),
                }
                for d in domain_names
            ],
            "summary": {
                "total": len(tools),
                "enabled": sum(1 for t in tools if t.get("enabled")),
                "disabled": sum(1 for t in tools if not t.get("enabled")),
                "write_tools": sum(1 for t in tools if t.get("governance") != "read"),
                "domain_count": len(domain_names),
            },
        }
    return catalog
