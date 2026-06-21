"""Amazon CloudWatch Logs Insights client."""

from __future__ import annotations

import time
from typing import Any

from backend.aws.session import aws_call, aws_client, assert_service_allowed
from backend.aws.time_range import resolve_time_range
from backend.models.config import AlfredConfig

SERVICE = "cloudwatch"


class CloudWatchLogsClient:
    def __init__(self, config: AlfredConfig) -> None:
        self._config = config
        self._client = aws_client(config, SERVICE)

    @classmethod
    def from_config(cls, config: AlfredConfig) -> CloudWatchLogsClient:
        if not config.aws.enabled:
            raise RuntimeError("AWS integration is disabled.")
        assert_service_allowed(config, SERVICE)
        return cls(config)

    def resolve_log_group(
        self,
        *,
        log_group: str | None = None,
        service_name: str | None = None,
    ) -> str:
        explicit = (log_group or "").strip()
        if explicit:
            return explicit

        name = (service_name or "").strip()
        if not name:
            raise ValueError("Either log_group or service_name is required.")

        mapped = self._lookup_service_map(name)
        if mapped:
            return mapped

        matches = self.find_log_groups(name, limit=5)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            joined = ", ".join(f"`{item}`" for item in matches)
            raise ValueError(
                f"Multiple log groups match service '{name}': {joined}. "
                "Pass log_group explicitly or add aws.log_group_map in config."
            )

        raise ValueError(
            f"No CloudWatch log group found for service '{name}'. "
            "Pass log_group=, configure aws.log_group_map, or run list_cloudwatch_log_groups."
        )

    def _lookup_service_map(self, service_name: str) -> str | None:
        mapping = self._config.aws.log_group_map or {}
        needle = service_name.lower()
        for key, value in mapping.items():
            if str(key).lower() == needle:
                return str(value).strip()
        return None

    def find_log_groups(self, prefix_or_name: str, *, limit: int = 25) -> list[str]:
        needle = (prefix_or_name or "").strip()
        if not needle:
            raise ValueError("prefix_or_name is required.")

        found: list[str] = []
        seen: set[str] = set()
        prefixes = [
            needle,
            f"/ecs/{needle}",
            f"/aws/lambda/{needle}",
            f"/aws/ecs/{needle}",
            f"/aws/apigateway/{needle}",
        ]

        paginator = self._client.get_paginator("describe_log_groups")
        for prefix in prefixes:
            for page in self._paginate_log_groups(paginator, logGroupNamePrefix=prefix):
                for group in page.get("logGroups") or []:
                    name = str(group.get("logGroupName") or "")
                    if name and name not in seen:
                        seen.add(name)
                        found.append(name)
                        if len(found) >= limit:
                            return found

        if found:
            return found

        needle_lower = needle.lower()
        for page in self._paginate_log_groups(paginator):
            for group in page.get("logGroups") or []:
                name = str(group.get("logGroupName") or "")
                if name and needle_lower in name.lower() and name not in seen:
                    seen.add(name)
                    found.append(name)
                    if len(found) >= limit:
                        return found
        return found

    def _paginate_log_groups(self, paginator: Any, **kwargs: Any) -> list[dict[str, Any]]:
        def _run() -> list[dict[str, Any]]:
            return list(paginator.paginate(**kwargs))

        return aws_call(self._config, SERVICE, "DescribeLogGroups", _run)

    def run_query(
        self,
        query: str,
        *,
        log_group: str | None = None,
        service_name: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 100,
        max_wait_seconds: int = 60,
    ) -> dict[str, Any]:
        insights_query = (query or "").strip()
        if not insights_query:
            raise ValueError("query is required.")

        group = self.resolve_log_group(log_group=log_group, service_name=service_name)
        start, end = resolve_time_range(start_time, end_time)
        row_limit = max(1, min(int(limit or 100), 1000))

        start_response = aws_call(
            self._config,
            SERVICE,
            "StartQuery",
            lambda: self._client.start_query(
                logGroupName=group,
                startTime=int(start.timestamp()),
                endTime=int(end.timestamp()),
                queryString=insights_query,
                limit=row_limit,
            ),
        )
        query_id = start_response["queryId"]
        deadline = time.monotonic() + max(5, min(max_wait_seconds, 300))
        status = "Running"
        statistics: dict[str, Any] = {}

        while time.monotonic() < deadline:
            result = aws_call(
                self._config,
                SERVICE,
                "GetQueryResults",
                lambda: self._client.get_query_results(queryId=query_id),
            )
            status = str(result.get("status") or "Unknown")
            statistics = result.get("statistics") or {}
            if status in {"Complete", "Failed", "Cancelled", "Timeout"}:
                if status != "Complete":
                    raise RuntimeError(f"CloudWatch Logs query {status.lower()} for `{group}`.")
                rows = self._parse_rows(result.get("results") or [])
                return {
                    "log_group": group,
                    "service_name": service_name or "",
                    "query": insights_query,
                    "query_id": query_id,
                    "start_time": start.isoformat(),
                    "end_time": end.isoformat(),
                    "columns": list(rows[0].keys()) if rows else [],
                    "rows": rows,
                    "row_count": len(rows),
                    "statistics": statistics,
                }
            time.sleep(1)

        raise RuntimeError(
            f"CloudWatch Logs query timed out after {max_wait_seconds}s (query id: {query_id})."
        )

    def _parse_rows(self, raw_rows: list[list[dict[str, str]]]) -> list[dict[str, str]]:
        parsed: list[dict[str, str]] = []
        for raw in raw_rows:
            row: dict[str, str] = {}
            for field in raw:
                key = str(field.get("field") or "")
                if key.startswith("@"):
                    key = key[1:]
                row[key] = str(field.get("value") or "")
            parsed.append(row)
        return parsed
