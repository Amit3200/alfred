"""Tests for AWS agent tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.models.config import AWSConfig, AlfredConfig
from backend.tools.git_api import build_git_tool_registry
from backend.tools.result import ToolResult


def _config(**aws_overrides) -> AlfredConfig:
    defaults = dict(
        enabled=True,
        profile="default",
        region="ap-south-1",
        allowed_services=["cloudwatch", "athena"],
        athena_database="analytics",
        athena_output_location="s3://bucket/athena/",
        log_group_map={"checkout-api": "/ecs/checkout-api"},
    )
    defaults.update(aws_overrides)
    config = AlfredConfig()
    config.aws = AWSConfig(**defaults)
    return config


@patch("backend.tools.aws_tool.AthenaClient")
def test_athena_query_tool(mock_client_cls):
    client = MagicMock()
    mock_client_cls.from_config.return_value = client
    client.run_query.return_value = {
        "query_execution_id": "abc",
        "database": "analytics",
        "columns": ["id"],
        "rows": [{"id": "1"}],
        "row_count": 1,
        "bytes_scanned": 100,
        "query": "SELECT 1",
    }

    registry = build_git_tool_registry(_config())
    result = registry.run(
        "athena_query",
        {"query": "SELECT 1"},
        allowed=["athena_query"],
    )

    assert isinstance(result, ToolResult)
    assert result.kind == "athena_query"
    assert result.data["row_count"] == 1


@patch("backend.tools.aws_tool.CloudWatchLogsClient")
def test_cloudwatch_query_tool(mock_client_cls):
    client = MagicMock()
    mock_client_cls.from_config.return_value = client
    client.run_query.return_value = {
        "log_group": "/ecs/checkout-api",
        "columns": ["timestamp", "message"],
        "rows": [{"timestamp": "t", "message": "error"}],
        "row_count": 1,
    }

    registry = build_git_tool_registry(_config())
    result = registry.run(
        "cloudwatch_query",
        {
            "query": "fields @timestamp, @message",
            "service_name": "checkout-api",
        },
        allowed=["cloudwatch_query"],
    )

    assert result.kind == "cloudwatch_query"
    client.run_query.assert_called_once()


@patch("backend.tools.aws_tool.CloudWatchLogsClient")
def test_list_cloudwatch_log_groups_tool(mock_client_cls):
    client = MagicMock()
    mock_client_cls.from_config.return_value = client
    client.find_log_groups.return_value = ["/ecs/checkout-api"]

    registry = build_git_tool_registry(_config())
    result = registry.run(
        "list_cloudwatch_log_groups",
        {"prefix_or_name": "checkout"},
        allowed=["list_cloudwatch_log_groups"],
    )

    assert result.kind == "cloudwatch_log_groups"
    assert result.data["groups"] == ["/ecs/checkout-api"]


@patch("backend.tools.aws_tool.AthenaClient")
def test_athena_permission_error_surfaces(mock_client_cls):
    client = MagicMock()
    mock_client_cls.from_config.return_value = client
    client.run_query.side_effect = RuntimeError(
        "AWS athena: permission denied for StartQueryExecution (AccessDenied). "
        "Grant the required IAM action or add 'athena' to aws.allowed_services."
    )

    registry = build_git_tool_registry(_config())
    result = registry.run("athena_query", {"query": "SELECT 1"}, allowed=["athena_query"])

    assert result.kind == "error"
    assert "permission denied" in result.data["message"].lower()


def test_service_not_allowed():
    config = _config(allowed_services=["cloudwatch"])
    registry = build_git_tool_registry(config)
    result = registry.run("athena_query", {"query": "SELECT 1"}, allowed=["athena_query"])
    assert result.kind == "error"
    assert "not enabled" in result.data["message"].lower()
