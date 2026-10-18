"""Discover class-based tool bundles for catalog and chaining."""

from __future__ import annotations

from collections.abc import Iterator

from backend.tools.base.bundle import ToolBundle


def iter_tool_bundles() -> Iterator[ToolBundle]:
    """Yield every domain ToolBundle that implements the class-tool contract."""
    from backend.tools.artifacts.bundle import ArtifactToolBundle
    from backend.tools.aws.bundle import AwsToolBundle
    from backend.tools.git.bundle import (
        GitApiToolBundle,
        GitLocalToolBundle,
        GitWriteToolBundle,
        GraphifyToolBundle,
    )
    from backend.tools.google.bundle import GoogleDocToolBundle, GoogleSheetToolBundle
    from backend.tools.jira.bundle import IdentityToolBundle, JiraToolBundle
    from backend.tools.repo_docs.bundle import RepoDocsToolBundle
    from backend.tools.schedule.bundle import ScheduleToolBundle
    from backend.tools.scripts.bundle import ScriptToolBundle
    from backend.tools.slack.board_tools import SlackBoardToolBundle
    from backend.tools.slack.register import SlackReadToolBundle
    from backend.tools.web.bundle import WebToolBundle
    from backend.tools.connectors.bundle import ConnectorToolBundle

    yield JiraToolBundle()
    yield IdentityToolBundle()
    yield SlackBoardToolBundle()
    yield SlackReadToolBundle()
    yield GitApiToolBundle()
    yield GitLocalToolBundle()
    yield GitWriteToolBundle()
    yield GraphifyToolBundle()
    yield GoogleSheetToolBundle()
    yield GoogleDocToolBundle()
    yield AwsToolBundle()
    yield ScriptToolBundle()
    yield WebToolBundle()
    yield ConnectorToolBundle()
    yield ScheduleToolBundle()
    yield RepoDocsToolBundle()
    yield ArtifactToolBundle()
