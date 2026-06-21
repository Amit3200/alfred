"""List custom Slack workspace emojis for status-line configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

EmojiKind = Literal["custom", "alias"]


@dataclass(frozen=True)
class WorkspaceEmoji:
    name: str
    kind: EmojiKind
    target: str | None = None

    @property
    def shortcode(self) -> str:
        return f":{self.name}:"

    @property
    def target_shortcode(self) -> str | None:
        if not self.target:
            return None
        return f":{self.target}:"


def slack_bot_client(bot_token: str) -> Any:
    from slack_sdk import WebClient

    return WebClient(token=bot_token)


def _emoji_list_error_message(response: dict[str, Any]) -> str:
    error = str(response.get("error") or "unknown_error")
    if error == "missing_scope":
        needed = str(response.get("needed") or "emoji:read")
        return (
            f"Slack bot is missing scope `{needed}` for emoji.list.\n"
            "Fix: api.slack.com/apps → your Alfred app → OAuth & Permissions → "
            "Bot Token Scopes → add `emoji:read` → Save → Reinstall to Workspace.\n"
            "Then paste the new bot token in Admin → Secrets and run `alfred slack emojis` again.\n"
            "(Custom emojis in thinking status still work without this scope — only listing them needs it.)"
        )
    return f"Slack emoji.list failed: {error}"


def _exception_error_message(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, dict) and not response.get("ok"):
        return _emoji_list_error_message(response)
    text = str(exc)
    if "missing_scope" in text and "emoji:read" in text:
        return _emoji_list_error_message({"ok": False, "error": "missing_scope", "needed": "emoji:read"})
    return text


def fetch_workspace_emojis(client: Any) -> list[WorkspaceEmoji]:
    """Return workspace emoji names from Slack emoji.list."""
    try:
        response = client.emoji_list()
    except Exception as exc:
        raise RuntimeError(_exception_error_message(exc)) from exc

    if not response.get("ok"):
        raise RuntimeError(_emoji_list_error_message(response))

    raw = response.get("emoji") or {}
    items: list[WorkspaceEmoji] = []
    for name, value in raw.items():
        text = str(value or "")
        if text.startswith("alias:"):
            items.append(WorkspaceEmoji(name=name, kind="alias", target=text.removeprefix("alias:")))
        elif text.startswith("http://") or text.startswith("https://"):
            items.append(WorkspaceEmoji(name=name, kind="custom"))
    items.sort(key=lambda item: item.name.lower())
    return items


def filter_workspace_emojis(
    emojis: list[WorkspaceEmoji],
    *,
    search: str | None = None,
    include_aliases: bool = False,
    custom_only: bool = True,
) -> list[WorkspaceEmoji]:
    query = (search or "").strip().lower()
    filtered: list[WorkspaceEmoji] = []
    for item in emojis:
        if custom_only and item.kind != "custom":
            if not include_aliases:
                continue
        elif not include_aliases and item.kind == "alias":
            continue
        if query and query not in item.name.lower():
            continue
        filtered.append(item)
    return filtered


def example_loading_line(name: str) -> str:
    label = name.replace("-", " ").replace("_", " ").strip()
    if not label:
        label = name
    return f":{name}: {label[0].upper()}{label[1:]}…"


def format_emojis_yaml(emojis: list[WorkspaceEmoji], *, limit: int = 8) -> str:
    lines = ["loading_messages:"]
    for item in emojis[:limit]:
        lines.append(f'  - "{example_loading_line(item.name)}"')
    return "\n".join(lines)
