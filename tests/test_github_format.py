"""Tests for GitHub comment formatting."""

from __future__ import annotations

from backend.ingress.github_format import format_for_github


def test_fenced_pipe_table_becomes_gfm():
    raw = "\n".join(
        [
            "## 2. Impact Matrix & Blast Radius",
            "```",
            "File Path | Impact Risk | Downstream Components | Breaking?",
            "----------------------------------+-------------+-----------------------+----------",
            "payload-builder/utils.ts | Med | acr-checkout.ts, abandoned-session.ts | Behavior change",
            "payload-builder/acr-checkout.ts | Low | index.ts | Backward-compatible",
            "```",
        ]
    )
    out = format_for_github(raw)
    assert "| File Path | Impact Risk | Downstream Components | Breaking? |" in out
    assert "| --- | --- | --- | --- |" in out
    assert "| payload-builder/utils.ts | Med |" in out
    assert "```" not in out


def test_gfm_table_preserved():
    raw = "\n".join(
        [
            "| File Path | Impact Risk |",
            "| --- | --- |",
            "| `utils.ts` | Low |",
        ]
    )
    out = format_for_github(raw)
    assert "| File Path | Impact Risk |" in out
    assert "`utils.ts`" in out
