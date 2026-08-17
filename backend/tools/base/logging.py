"""Structured logging for tool execution."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.tools.catalog import tool_category, tool_domain

_REDACT_KEYS = frozenset({"api_token", "credentials", "password", "credentials_json", "oauth_refresh_token"})
_TEXT_KEYS = frozenset({"comment", "body_text", "text", "description", "summary", "values"})


def domain_logger(domain: str) -> logging.Logger:
    return logging.getLogger(f"alfred.tools.{domain}")


def redact_args(args: dict[str, Any]) -> dict[str, Any]:
    """Return a log-safe copy of tool arguments."""
    redacted: dict[str, Any] = {}
    for key, value in (args or {}).items():
        lower = key.lower()
        if lower in _REDACT_KEYS:
            redacted[key] = "[REDACTED]"
        elif lower in _TEXT_KEYS:
            text = str(value)
            redacted[key] = text[:200] + ("…" if len(text) > 200 else "")
        elif lower in {"rows", "values"}:
            if isinstance(value, list):
                cols = len(value[0]) if value and isinstance(value[0], list) else 0
                redacted[key] = {"row_count": len(value), "col_count": cols}
            else:
                redacted[key] = {"raw_len": len(str(value))}
        else:
            redacted[key] = value
    return redacted


@dataclass
class ToolExecutionLog:
    tool_name: str
    domain: str
    operation: str
    task_id: str | None
    session_key: str | None
    started_at: datetime
    args_redacted: dict[str, Any] = field(default_factory=dict)
    finished_at: datetime | None = None
    duration_ms: int | None = None
    success: bool | None = None
    result_kind: str | None = None
    error: str | None = None

    @classmethod
    def start(
        cls,
        *,
        tool_name: str,
        operation: str,
        args: dict[str, Any],
        task_id: str | None = None,
        session_key: str | None = None,
    ) -> ToolExecutionLog:
        domain = tool_domain(tool_name)
        log = cls(
            tool_name=tool_name,
            domain=domain,
            operation=operation,
            task_id=task_id,
            session_key=session_key,
            started_at=datetime.now(timezone.utc),
            args_redacted=redact_args(args),
        )
        domain_logger(domain).info(
            "tool_start name=%s domain=%s operation=%s task_id=%s args=%s",
            tool_name,
            domain,
            operation,
            task_id,
            log.args_redacted,
        )
        return log

    def finish(
        self,
        *,
        success: bool,
        result_kind: str | None = None,
        error: str | None = None,
    ) -> None:
        self.finished_at = datetime.now(timezone.utc)
        self.duration_ms = int((self.finished_at - self.started_at).total_seconds() * 1000)
        self.success = success
        self.result_kind = result_kind
        self.error = error
        logger = domain_logger(self.domain)
        if success:
            logger.info(
                "tool_done name=%s domain=%s duration_ms=%s result_kind=%s category=%s",
                self.tool_name,
                self.domain,
                self.duration_ms,
                result_kind,
                tool_category(self.tool_name),
            )
        elif error:
            logger.warning(
                "tool_fail name=%s domain=%s duration_ms=%s error=%s",
                self.tool_name,
                self.domain,
                self.duration_ms,
                error,
            )
        else:
            logger.error(
                "tool_error name=%s domain=%s duration_ms=%s",
                self.tool_name,
                self.domain,
                self.duration_ms,
            )
