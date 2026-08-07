"""Runtime governance context attached to ToolRegistry."""

from __future__ import annotations

from typing import Any

from backend.governance.audit import get_audit_store
from backend.governance.catalog import is_write_tool, requires_confirmation, tool_action_summary
from backend.governance.confirmation import (
    confirmation_required_message,
    session_has_write_approval,
)
from backend.governance.policies import check_write_policy
from backend.models.config import AlfredConfig
from backend.models.session import ConversationSession
from backend.models.task import Task
from backend.tools.result import ToolResult


class GovernanceContext:
    def __init__(
        self,
        config: AlfredConfig,
        task: Task,
        *,
        session: ConversationSession | None = None,
        skill_name: str | None = None,
        data_dir: Any = None,
    ) -> None:
        self.config = config
        self.task = task
        self.session = session
        self.skill_name = skill_name or ""
        self.data_dir = data_dir
        self._gov = config.governance

    @property
    def enabled(self) -> bool:
        return bool(self._gov.enabled)

    def check_before_run(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult | None:
        if not self.enabled or not is_write_tool(tool_name):
            return None

        policy_error = check_write_policy(tool_name, self.task, self.config)
        if policy_error:
            self._audit(tool_name, arguments, kind="policy_block", success=False, message=policy_error, blocked=True)
            return ToolResult.error(policy_error)

        if requires_confirmation(tool_name):
            if self._confirmation_required_for_source():
                if not self._tool_auto_approved(tool_name):
                    if not session_has_write_approval(self.session, self._gov):
                        summary = tool_action_summary(tool_name, arguments)
                        msg = confirmation_required_message(tool_name, summary)
                        self._audit(
                            tool_name,
                            arguments,
                            kind="confirmation_required",
                            success=False,
                            message=msg,
                            blocked=True,
                        )
                        return ToolResult.error(msg)

        return None

    def _tool_auto_approved(self, tool_name: str) -> bool:
        if tool_name in self._gov.auto_approve_tools:
            return True
        sync = self.config.slack.list_jira_sync
        if (
            sync.enabled
            and sync.auto_approve_jira_create
            and tool_name == "jira_create_issue"
        ):
            from backend.integrations.slack.list_jira_sync import sync_channel_allowed

            return sync_channel_allowed(self.task.channel_id or "", self.config)
        if tool_name.startswith("slack_board_") and self.config.slack.board_workflows.enabled:
            from backend.integrations.slack.board_service import resolve_board_for_task

            board = resolve_board_for_task(self.config, self.task, data_dir=self.data_dir)
            if board and board.auto_approve_writes:
                return True
        return False

    def _confirmation_required_for_source(self) -> bool:
        if not self._gov.require_confirmation:
            return False
        source = self.task.source
        allowed = self._gov.require_confirmation_sources
        if not allowed:
            return source in ("slack", "ui")
        return source in allowed

    def audit_after_run(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: ToolResult,
    ) -> None:
        if not self.enabled or not self._gov.audit_enabled:
            return
        if not is_write_tool(tool_name):
            return
        message = ""
        if result.kind == "error":
            message = str(result.data.get("message") or "")
        self._audit(
            tool_name,
            arguments,
            kind=result.kind,
            success=result.kind != "error",
            message=message,
            blocked=False,
        )

    def _audit(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        kind: str,
        success: bool,
        message: str,
        blocked: bool,
    ) -> None:
        if not self._gov.audit_enabled:
            return
        from backend.models.session import task_session_key

        get_audit_store(self.data_dir).log(
            {
                "task_id": self.task.id,
                "session_key": task_session_key(self.task) or "",
                "source": self.task.source,
                "user_id": self.task.user_id,
                "channel_id": self.task.channel_id,
                "skill_name": self.skill_name,
                "tool_name": tool_name,
                "tool_args": arguments,
                "result_kind": kind,
                "success": success,
                "message": message,
                "blocked": blocked,
            }
        )
