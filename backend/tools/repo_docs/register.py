"""Register class-based repo documentation tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.models.config import AlfredConfig
from backend.tools.registry import ToolRegistry
from backend.tools.repo_docs.bundle import RepoDocsToolBundle
from backend.tools.repo_docs.schemas import REPO_DOC_TOOL_NAMES

__all__ = ["REPO_DOC_TOOL_NAMES", "register_repo_doc_tools"]


def register_repo_doc_tools(
    registry: ToolRegistry,
    config: AlfredConfig,
    *,
    data_dir: Any,
) -> None:
    if not config.repo_knowledge.enabled or not config.git.enabled:
        return
    registry.alfred_config = config
    if data_dir is not None:
        registry.data_dir = Path(data_dir)
    RepoDocsToolBundle().register(registry)
