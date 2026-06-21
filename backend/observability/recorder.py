"""Record AI and tool interactions to the observability store."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from backend.ai.base import LLMResponse
from backend.observability.context import InteractionContext, get_interaction_context
from backend.observability.models import InteractionEvent
from backend.observability.store import ObservabilityStore, SQLiteObservabilityStore
from backend.observability.tools import tool_category
from backend.observability.usage import parse_token_usage
from backend.paths import get_data_dir

logger = logging.getLogger(__name__)


class ObservabilityRecorder:
    def __init__(self, store: ObservabilityStore) -> None:
        self.store = store

    def record_llm_call(
        self,
        response: LLMResponse,
        *,
        duration_ms: int,
        ctx: InteractionContext | None = None,
    ) -> None:
        ctx = ctx or get_interaction_context()
        if ctx is None:
            ctx = InteractionContext(source="unknown", user_label="unknown")

        prompt, completion, total = parse_token_usage(response.provider, response.raw)
        event = InteractionEvent(
            recorded_at=datetime.now(timezone.utc),
            event_type="llm_call",
            source=ctx.source,
            user_id=ctx.user_id,
            user_label=ctx.user_label or ctx.user_id or "unknown",
            task_id=ctx.task_id,
            session_key=ctx.session_key,
            provider=response.provider,
            model=response.model,
            call_kind=ctx.call_kind,
            skill_name=ctx.skill_name,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            duration_ms=duration_ms,
            metadata=dict(ctx.metadata),
        )
        try:
            self.store.record(event)
        except Exception:
            logger.exception("Failed to record LLM observability event")

    def record_tool_call(
        self,
        tool_name: str,
        *,
        success: bool = True,
        duration_ms: int | None = None,
        ctx: InteractionContext | None = None,
    ) -> None:
        ctx = ctx or get_interaction_context()
        if ctx is None:
            ctx = InteractionContext(source="unknown", user_label="unknown")

        event = InteractionEvent(
            recorded_at=datetime.now(timezone.utc),
            event_type="tool_call",
            source=ctx.source,
            user_id=ctx.user_id,
            user_label=ctx.user_label or ctx.user_id or "unknown",
            task_id=ctx.task_id,
            session_key=ctx.session_key,
            call_kind=ctx.call_kind,
            skill_name=ctx.skill_name,
            duration_ms=duration_ms,
            tool_name=tool_name,
            tool_category=tool_category(tool_name),
            success=success,
            metadata=dict(ctx.metadata),
        )
        try:
            self.store.record(event)
        except Exception:
            logger.exception("Failed to record tool observability event")


@lru_cache(maxsize=8)
def _recorder_for_dir(data_dir_str: str) -> ObservabilityRecorder:
    store = SQLiteObservabilityStore(Path(data_dir_str))
    return ObservabilityRecorder(store)


def get_recorder(data_dir: Path | None = None) -> ObservabilityRecorder:
    path = get_data_dir(data_dir)
    return _recorder_for_dir(str(path))
