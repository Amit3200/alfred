"""Parse token usage from provider-specific LLM responses."""

from __future__ import annotations

from typing import Any


def parse_token_usage(provider: str, raw: dict[str, Any] | None) -> tuple[int, int, int]:
    """Return (prompt_tokens, completion_tokens, total_tokens)."""
    if not raw:
        return 0, 0, 0

    usage = raw.get("usage")
    if not isinstance(usage, dict):
        return 0, 0, 0

    if provider == "anthropic":
        prompt = int(usage.get("input_tokens") or 0)
        completion = int(usage.get("output_tokens") or 0)
    else:
        prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion = int(
            usage.get("completion_tokens") or usage.get("output_tokens") or 0
        )

    total = int(usage.get("total_tokens") or (prompt + completion))
    return prompt, completion, total
