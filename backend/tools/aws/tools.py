"""AWS Athena / CloudWatch FunctionTools."""

from __future__ import annotations

from typing import Any

from backend.ai.base import ToolSchema
from backend.integrations.aws.athena import AthenaClient
from backend.integrations.aws.cloudwatch_logs import CloudWatchLogsClient
from backend.tools.base.function_tool import FunctionTool
from backend.tools.base.tool import BaseTool, ToolContext
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
            "query": {"type": "string", "description": "SQL query to execute."},
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
            "limit": {"type": "integer", "description": "Max groups to return (default 25)."},
        },
        "required": ["prefix_or_name"],
    },
)


def _enforce_athena_guardrails(sql: str) -> str:
    cleaned = sql.strip().rstrip(";")
    lower = cleaned.lower()
    if not lower.startswith("select") or "limit" in lower:
        return cleaned
    return f"{cleaned}\nLIMIT 200"


def athena_query(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    try:
        client = AthenaClient.from_config(ctx.config)
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


def cloudwatch_query(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    try:
        client = CloudWatchLogsClient.from_config(ctx.config)
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


def list_cloudwatch_log_groups(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    prefix = str(args.get("prefix_or_name") or "").strip()
    if not prefix:
        return ToolResult.error("prefix_or_name is required.")
    try:
        client = CloudWatchLogsClient.from_config(ctx.config)
        groups = client.find_log_groups(prefix, limit=int(args.get("limit") or 25))
        return ToolResult.cloudwatch_log_groups(groups, prefix=prefix)
    except (RuntimeError, ValueError) as exc:
        return ToolResult.error(str(exc))


def aws_tools() -> list[BaseTool]:
    return [
        FunctionTool(
            name="athena_query",
            capability="aws.read.query",
            operation="athena",
            domain="aws",
            schema=ATHENA_QUERY,
            run_fn=athena_query,
            produces=("rows",),
        ),
        FunctionTool(
            name="cloudwatch_query",
            capability="aws.read.query",
            operation="cloudwatch",
            domain="aws",
            schema=CLOUDWATCH_QUERY,
            run_fn=cloudwatch_query,
            produces=("logs",),
        ),
        FunctionTool(
            name="list_cloudwatch_log_groups",
            capability="aws.read.query",
            operation="list_log_groups",
            domain="aws",
            schema=LIST_CLOUDWATCH_LOG_GROUPS,
            run_fn=list_cloudwatch_log_groups,
            produces=("log_groups",),
            next_tools=("cloudwatch_query",),
        ),
    ]
