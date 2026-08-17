"""Admin API for routing traces and capability bundles."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.deps import require_admin
from backend.config_manager import ConfigManager
from backend.routing.capabilities import load_capability_bundles
from backend.routing.trace_store import get_trace, list_traces

router = APIRouter(prefix="/routing", tags=["routing"])


@router.get("/traces")
def get_routing_traces(
    limit: int = Query(default=50, ge=1, le=200),
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    traces = list_traces(manager.data_dir, limit=limit)
    return {"traces": traces, "count": len(traces)}


@router.get("/traces/{task_id}")
def get_routing_trace(
    task_id: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    record = get_trace(manager.data_dir, task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Routing trace not found")
    return record


@router.get("/capabilities")
def get_capability_bundles(
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    bundles = load_capability_bundles(manager.data_dir)
    payload = {
        name: {
            "tools": sorted(bundle.tools),
            "policy_name": bundle.policy_name,
            "context_injectors": list(bundle.context_injectors),
            "subagent": bundle.subagent,
            "output_format": bundle.output_format,
        }
        for name, bundle in bundles.items()
    }
    return {"bundles": payload, "count": len(payload)}
