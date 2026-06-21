"""Amazon Athena query client."""

from __future__ import annotations

import time
from typing import Any

from backend.aws.session import aws_call, aws_client, assert_service_allowed
from backend.models.config import AlfredConfig

SERVICE = "athena"


class AthenaClient:
    def __init__(self, config: AlfredConfig) -> None:
        self._config = config
        self._client = aws_client(config, SERVICE)

    @classmethod
    def from_config(cls, config: AlfredConfig) -> AthenaClient:
        if not config.aws.enabled:
            raise RuntimeError("AWS integration is disabled.")
        assert_service_allowed(config, SERVICE)
        return cls(config)

    def run_query(
        self,
        query: str,
        *,
        database: str | None = None,
        workgroup: str | None = None,
        output_location: str | None = None,
        max_wait_seconds: int = 120,
    ) -> dict[str, Any]:
        sql = (query or "").strip()
        if not sql:
            raise ValueError("query is required.")

        db = (database or self._config.aws.athena_database or "").strip()
        if not db:
            raise ValueError(
                "Athena database is required. Pass database= or set aws.athena_database in config."
            )

        wg = (workgroup or self._config.aws.athena_workgroup or "primary").strip()
        output = (output_location or self._config.aws.athena_output_location or "").strip()
        if not output:
            raise ValueError(
                "Athena output location is required. Pass output_location= (s3://bucket/prefix/) "
                "or set aws.athena_output_location in config."
            )

        execution = aws_call(
            self._config,
            SERVICE,
            "StartQueryExecution",
            lambda: self._client.start_query_execution(
                QueryString=sql,
                QueryExecutionContext={"Database": db},
                ResultConfiguration={"OutputLocation": output},
                WorkGroup=wg,
            ),
        )
        execution_id = execution["QueryExecutionId"]
        deadline = time.monotonic() + max(5, min(max_wait_seconds, 600))
        state = "RUNNING"
        status_detail = ""
        bytes_scanned = 0

        while time.monotonic() < deadline:
            result = aws_call(
                self._config,
                SERVICE,
                "GetQueryExecution",
                lambda: self._client.get_query_execution(QueryExecutionId=execution_id),
            )
            execution_info = result.get("QueryExecution") or {}
            status = execution_info.get("Status") or {}
            state = str(status.get("State") or "UNKNOWN")
            status_detail = str(status.get("StateChangeReason") or "")
            stats = execution_info.get("Statistics") or {}
            bytes_scanned = int(stats.get("DataScannedInBytes") or 0)
            if state in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                break
            time.sleep(1)

        if state == "RUNNING":
            aws_call(
                self._config,
                SERVICE,
                "StopQueryExecution",
                lambda: self._client.stop_query_execution(QueryExecutionId=execution_id),
            )
            raise RuntimeError(
                f"Athena query timed out after {max_wait_seconds}s (execution id: {execution_id})."
            )

        if state != "SUCCEEDED":
            reason = status_detail or state
            raise RuntimeError(f"Athena query {state.lower()}: {reason}")

        columns, rows = self._fetch_results(execution_id)
        return {
            "query_execution_id": execution_id,
            "database": db,
            "workgroup": wg,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "bytes_scanned": bytes_scanned,
            "query": sql,
        }

    def _fetch_results(self, execution_id: str) -> tuple[list[str], list[dict[str, str]]]:
        columns: list[str] = []
        rows: list[dict[str, str]] = []
        next_token: str | None = None
        header_seen = False

        while True:
            kwargs: dict[str, Any] = {"QueryExecutionId": execution_id, "MaxResults": 1000}
            if next_token:
                kwargs["NextToken"] = next_token

            page = aws_call(
                self._config,
                SERVICE,
                "GetQueryResults",
                lambda kwargs=kwargs: self._client.get_query_results(**kwargs),
            )

            for record in page.get("ResultSet", {}).get("Rows") or []:
                values = [cell.get("VarCharValue", "") for cell in record.get("Data") or []]
                if not header_seen:
                    columns = values
                    header_seen = True
                    continue
                row = {columns[i]: values[i] if i < len(values) else "" for i in range(len(columns))}
                rows.append(row)

            next_token = page.get("NextToken")
            if not next_token:
                break

        return columns, rows
