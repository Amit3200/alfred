"""AWS tools — Athena queries and CloudWatch Logs Insights."""

from __future__ import annotations

from typing import Any

from backend.ai.base import ToolSchema
from backend.integrations.aws.athena import AthenaClient
from backend.integrations.aws.cloudwatch_logs import CloudWatchLogsClient
from backend.models.config import AlfredConfig
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult

ATHENA_QUERY = ToolSchema(
    name="athena_query",
    description=(
        "Run a read-only SQL query against Amazon Athena. "
        "Use for dataset lookups, analytics tables, and incident data in S3/Glue catalogs."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "SQL query to execute.",
            },
            "database": {
                "type": "string",
                "description": "Glue/Athena database name. Defaults to aws.athena_database in config.",
            },
            "workgroup": {
                "type": "string",
                "description": "Athena workgroup. Defaults to aws.athena_workgroup (primary).",
            },
            "output_location": {
                "type": "string",
                "description": "S3 output prefix, e.g. s3://bucket/athena/. Defaults to config.",
            },
            "max_wait_seconds": {
                "type": "integer",
                "description": "Max seconds to wait for query completion (default 120).",
            },
        },
        "required": ["query"],
    },
)

CLOUDWATCH_QUERY = ToolSchema(
    name="cloudwatch_query",
    description=(
        "Run a CloudWatch Logs Insights query against a log group. "
        "Pass log_group directly or service_name to resolve via aws.log_group_map / common ECS paths."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Logs Insights query, e.g. fields @timestamp, @message | filter @message like /error/.",
            },
            "log_group": {
                "type": "string",
                "description": "Exact CloudWatch log group name, e.g. /ecs/checkout-api.",
            },
            "service_name": {
                "type": "string",
                "description": "Short service name to resolve to a log group when log_group is omitted.",
            },
            "start_time": {
                "type": "string",
                "description": "Start time — ISO8601 or relative (30m, 1h, 24h, 7d). Default: 1h ago.",
            },
            "end_time": {
                "type": "string",
                "description": "End time — ISO8601 or relative. Default: now.",
            },
            "limit": {
                "type": "integer",
                "description": "Max log rows to return (default 100, max 1000).",
            },
            "max_wait_seconds": {
                "type": "integer",
                "description": "Max seconds to wait for query completion (default 60).",
            },
        },
        "required": ["query"],
    },
)

LIST_CLOUDWATCH_LOG_GROUPS = ToolSchema(
    name="list_cloudwatch_log_groups",
    description=(
        "List or search CloudWatch log groups by prefix or service name. "
        "Use to discover log group paths before running cloudwatch_query."
    ),
    parameters={
        "type": "object",
        "properties": {
            "prefix_or_name": {
                "type": "string",
                "description": "Prefix or substring to match, e.g. checkout-api or /ecs/.",
            },
            "limit": {
                "type": "integer",
                "description": "Max groups to return (default 25).",
            },
        },
        "required": ["prefix_or_name"],
    },
)


def _enforce_athena_guardrails(sql: str) -> str:
    """Append a default LIMIT to bare SELECT queries."""
    cleaned = sql.strip().rstrip(";")
    lower = cleaned.lower()
    if not lower.startswith("select") or "limit" in lower:
        return cleaned
    return f"{cleaned}\nLIMIT 200"


def register_aws_tools(registry: ToolRegistry, config: AlfredConfig) -> None:
    if not config.aws.enabled:
        return

    def athena_handler(args: dict[str, Any]) -> ToolResult:
        try:
            client = AthenaClient.from_config(config)
            query = _enforce_athena_guardrails(str(args.get("query") or ""))
            data = client.run_query(
                query,
                database=str(args.get("database") or "") or None,
                workgroup=str(args.get("workgroup") or "") or None,
                output_location=str(args.get("output_location") or "") or None,
                max_wait_seconds=int(args.get("max_wait_seconds") or 120),
            )
            return ToolResult.athena_query(data)
        except (RuntimeError, ValueError) as exc:
            return ToolResult.error(str(exc))

    def cloudwatch_handler(args: dict[str, Any]) -> ToolResult:
        try:
            client = CloudWatchLogsClient.from_config(config)
            data = client.run_query(
                str(args.get("query") or ""),
                log_group=str(args.get("log_group") or "") or None,
                service_name=str(args.get("service_name") or "") or None,
                start_time=str(args.get("start_time") or "") or None,
                end_time=str(args.get("end_time") or "") or None,
                limit=int(args.get("limit") or 100),
                max_wait_seconds=int(args.get("max_wait_seconds") or 60),
            )
            return ToolResult.cloudwatch_query(data)
        except (RuntimeError, ValueError) as exc:
            return ToolResult.error(str(exc))

    def list_groups_handler(args: dict[str, Any]) -> ToolResult:
        prefix = str(args.get("prefix_or_name") or "").strip()
        if not prefix:
            return ToolResult.error("prefix_or_name is required.")
        try:
            client = CloudWatchLogsClient.from_config(config)
            groups = client.find_log_groups(prefix, limit=int(args.get("limit") or 25))
            return ToolResult.cloudwatch_log_groups(groups, prefix=prefix)
        except (RuntimeError, ValueError) as exc:
            return ToolResult.error(str(exc))

    registry.register(ATHENA_QUERY, athena_handler)
    registry.register(CLOUDWATCH_QUERY, cloudwatch_handler)
    registry.register(LIST_CLOUDWATCH_LOG_GROUPS, list_groups_handler)
