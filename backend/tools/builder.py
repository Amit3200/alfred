"""Build the process-wide tool registry from domain packages."""

from __future__ import annotations

from pathlib import Path

from backend.models.config import AlfredConfig
from backend.tools.catalog import (
    ARTIFACT_TOOLS,
    AWS_TOOLS,
    COMPANY_SCRIPT_TOOLS,
    CONNECTOR_TOOLS,
    GIT_TOOLS,
    GOOGLE_TOOLS,
    JIRA_MODULE_TOOLS,
    REPO_DOC_TOOLS,
    SCHEDULE_TOOLS,
    SLACK_TOOLS,
    WEB_TOOLS,
)
from backend.tools.google import register_google_tools
from backend.tools.jira import register_jira_tools
from backend.tools.registry import ToolRegistry
from backend.tools.selection import wants_module


def build_tool_registry(
    config: AlfredConfig,
    *,
    workspace_id: str | None = None,
    data_dir: Path | None = None,
    allowed_tools: list[str] | None = None,
) -> ToolRegistry:
    """Register every enabled domain's tools onto one registry."""
    registry = ToolRegistry()
    registry.clear_results()
    registry.set_registration_filter(allowed_tools)
    registry.git_config = config.git
    registry.workspace_id = workspace_id
    registry.data_dir = data_dir
    registry.alfred_config = config

    allowed = registry._registration_filter
    path = Path(data_dir) if data_dir is not None else None

    if wants_module(GIT_TOOLS, allowed):
        from backend.tools.git import register_git_tools

        register_git_tools(registry, config, data_dir=path)

    if wants_module(JIRA_MODULE_TOOLS, allowed):
        register_jira_tools(registry, config)

    if wants_module(AWS_TOOLS, allowed):
        from backend.tools.aws.register import register_aws_tools

        register_aws_tools(registry, config)

    if wants_module(GOOGLE_TOOLS, allowed):
        register_google_tools(registry, config)

    if wants_module(SLACK_TOOLS, allowed):
        from backend.tools.slack import register_slack_tools

        register_slack_tools(registry, config)
        if path is not None:
            from backend.tools.slack.board_register import register_slack_board_tools

            register_slack_board_tools(registry, config, data_dir=path)

    if wants_module(WEB_TOOLS, allowed):
        from backend.tools.web.register import register_web_search_tools

        register_web_search_tools(registry, config)

    if wants_module(CONNECTOR_TOOLS, allowed):
        from backend.tools.connectors.register import register_connector_tools

        register_connector_tools(registry, config)

    if wants_module(SCHEDULE_TOOLS, allowed):
        from backend.tools.schedule.register import register_schedule_tools

        register_schedule_tools(registry, data_dir)

    if wants_module(COMPANY_SCRIPT_TOOLS, allowed):
        from backend.tools.scripts.register import register_company_script_tools

        register_company_script_tools(registry, config=config, data_dir=data_dir)

    if wants_module(ARTIFACT_TOOLS, allowed):
        from backend.tools.artifacts.register import register_artifact_tools

        register_artifact_tools(registry, config=config, data_dir=data_dir)

    if (
        config.repo_knowledge.enabled
        and config.git.enabled
        and path is not None
        and wants_module(REPO_DOC_TOOLS, allowed)
    ):
        from backend.tools.repo_docs.register import register_repo_doc_tools

        register_repo_doc_tools(registry, config, data_dir=path)

    return registry


def build_git_tool_registry(
    config: AlfredConfig,
    *,
    workspace_id: str | None = None,
    data_dir: Path | None = None,
    allowed_tools: list[str] | None = None,
) -> ToolRegistry:
    """Historical name — same as ``build_tool_registry``."""
    return build_tool_registry(
        config,
        workspace_id=workspace_id,
        data_dir=data_dir,
        allowed_tools=allowed_tools,
    )
