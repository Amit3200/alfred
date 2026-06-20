"""Export UI chat sessions to Markdown files."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from backend.ingress.render import render_turn
from backend.models.session import ConversationSession
from backend.paths import exports_dir

_EXPORT_INTENT_RE = re.compile(
    r"\b(export|save|download).{0,24}(markdown|md|\.md)\b|"
    r"\b(export|save)\s+(this|chat|conversation|thread)\b",
    re.I,
)


def wants_export_markdown(text: str) -> bool:
    return bool(_EXPORT_INTENT_RE.search(text.strip()))


def session_to_markdown(session: ConversationSession) -> str:
    title = str(session.metadata.get("title") or "Alfred chat")
    lines = [
        f"# {title}",
        "",
        f"- **Chat ID:** `{session.scope_id}`",
        f"- **Exported:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"- **Messages:** {len(session.turns)}",
        "",
        "---",
        "",
    ]
    for turn in session.turns:
        heading = "You" if turn.role == "user" else "Alfred"
        lines.append(f"## {heading}")
        lines.append("")
        if turn.role == "assistant":
            lines.append(render_turn(turn.payload, turn.content, "ui"))
        else:
            lines.append(turn.content.strip())
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def export_session_markdown(
    session: ConversationSession,
    data_dir: Path | None = None,
    *,
    filename: str | None = None,
) -> Path:
    dest_dir = exports_dir(data_dir)
    if not filename:
        slug = re.sub(r"[^\w\-]+", "-", str(session.metadata.get("title") or "chat")).strip("-")[:40]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        filename = f"{slug or 'chat'}-{session.scope_id[:8]}-{stamp}.md"
    if not filename.endswith(".md"):
        filename = f"{filename}.md"
    path = dest_dir / filename
    path.write_text(session_to_markdown(session), encoding="utf-8")
    return path
