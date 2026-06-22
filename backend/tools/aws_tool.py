"""AWS tools — Athena queries and CloudWatch Logs Insights."""

from __future__ import annotations

from typing import Any

from backend.ai.base import ToolSchema
from backend.aws.athena import AthenaClient
from backend.aws.cloudwatch_logs import CloudWatchLogsClient
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

GRADE_EVENTS_QUERY = ToolSchema(
    name="grade_events_query",
    description=(
        "Query a configured grade_events Athena table with built-in guardrails. "
        "Requires a domain playbook in .alfred/playbooks/. Always applies LIMIT 200 unless full_data=true."
    ),
    parameters={
        "type": "object",
        "properties": {
            "kind": {"type": "string", "description": "Event kind filter."},
            "merchant_id": {"type": "string", "description": "Merchant ID filter."},
            "session_id": {"type": "string", "description": "Checkout session ID filter."},
            "fp_id": {"type": "string", "description": "AcmeCorp fp_id filter."},
            "environment": {"type": "string", "description": "Environment filter, e.g. production."},
            "category": {"type": "string", "description": "Event category filter."},
            "platform": {"type": "string", "description": "Platform filter."},
            "date": {
                "type": "string",
                "description": "Partition date YYYY-MM-DD.",
            },
            "date_from": {
                "type": "string",
                "description": "Inclusive start partition date YYYY-MM-DD.",
            },
            "date_to": {
                "type": "string",
                "description": "Inclusive end partition date YYYY-MM-DD.",
            },
            "hour": {
                "type": "string",
                "description": "Partition hour (00-23).",
            },
            "errors_only": {
                "type": "boolean",
                "description": "When true, only rows with non-empty error.",
            },
            "full_data": {
                "type": "boolean",
                "description": (
                    "Only set true when the user explicitly asks for full/unlimited data. "
                    "Otherwise capped at 200 rows."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Row limit when full_data=true (max 5000). Ignored otherwise (always 200).",
            },
            "max_wait_seconds": {
                "type": "integer",
                "description": "Max seconds to wait for Athena (default 120).",
            },
        },
        "required": [],
    },
)


def _enforce_athena_guardrails(sql: str) -> str:
    """Backup guardrail when grade_events is queried via raw athena_query."""
    cleaned = sql.strip().rstrip(";")
    lower = cleaned.lower()
    if "grade_events" not in lower or "limit" in lower:
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

    def grade_events_handler(args: dict[str, Any]) -> ToolResult:
        try:
            from backend.aws.grade_events import GradeEventsClient

            client = GradeEventsClient.from_config(config)
            data = client.query(
                kind=str(args.get("kind") or "") or None,
                merchant_id=str(args.get("merchant_id") or "") or None,
                session_id=str(args.get("session_id") or "") or None,
                fp_id=str(args.get("fp_id") or "") or None,
                environment=str(args.get("environment") or "") or None,
                category=str(args.get("category") or "") or None,
                platform=str(args.get("platform") or "") or None,
                date=str(args.get("date") or "") or None,
                date_from=str(args.get("date_from") or "") or None,
                date_to=str(args.get("date_to") or "") or None,
                hour=str(args.get("hour") or "") or None,
                errors_only=bool(args.get("errors_only")),
                full_data=bool(args.get("full_data")),
                limit=int(args.get("limit") or 200),
                max_wait_seconds=int(args.get("max_wait_seconds") or 120),
            )
            return ToolResult.grade_events_query(data)
        except (RuntimeError, ValueError) as exc:
            return ToolResult.error(str(exc))

    registry.register(ATHENA_QUERY, athena_handler)
    registry.register(CLOUDWATCH_QUERY, cloudwatch_handler)
    registry.register(LIST_CLOUDWATCH_LOG_GROUPS, list_groups_handler)
    registry.register(GRADE_EVENTS_QUERY, grade_events_handler)
