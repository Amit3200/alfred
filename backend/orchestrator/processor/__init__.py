"""TaskProcessor package — session, direct, investigation, reply."""

from backend.orchestrator.processor.core import TaskProcessor
from backend.orchestrator.processor.helpers import (
    STRUCTURED_TOOL_KINDS,
    _task_channel,
    _tool_result_to_response,
    _unified_metadata_patch,
    clean_message_text,
)

__all__ = [
    "TaskProcessor",
    "STRUCTURED_TOOL_KINDS",
    "_task_channel",
    "_tool_result_to_response",
    "_unified_metadata_patch",
    "clean_message_text",
]
