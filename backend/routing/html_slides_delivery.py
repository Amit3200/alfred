"""HTML slides delivery helpers — prompts, salvage, and intent detection."""

from __future__ import annotations

import re
from typing import Any

from backend.ai.base import Message
from backend.formatting.file_exports import extract_html_deck
from backend.models.task import Task
from backend.routing.tool_plan_types import ToolPlan, ToolPlanStep
from backend.tools.result import ToolResult

_HTML_SLIDES_RE = re.compile(
    r"\b("
    r"slide deck|html slides?|presentation|presentations|"
    r"create slides|creating slides|make slides|making slides|"
    r"build slides|building slides|html deck|slide show|slideshow|"
    r"generate a deck|build a deck|make a deck|"
    r"slides again|deck again|try again.*slides|retry.*slides"
    r")\b",
    re.I,
)

_SLIDES_FOLLOWUP_RE = re.compile(
    r"\b("
    r"try again|retry|again|one more time|"
    r"create slides|creating slides|make slides|build slides|"
    r"generate.*slides|generate.*presentation|generate.*deck"
    r")\b",
    re.I,
)

_PUBLISH_RE = re.compile(
    r"\b("
    r"publish|host|share link|share url|shareable|upload|"
    r"give me the link|link to access|public url|artifact url"
    r")\b",
    re.I,
)

_SLUG_RE = re.compile(r"\b[a-z0-9][a-z0-9-]{2,62}\b", re.I)

_EXPORT_FILENAME_RE = re.compile(
    r"(?:/api/chat/exports/|\.alfred/exports/|exports/)([a-zA-Z0-9._-]+\.html)",
    re.I,
)

ARTIFACT_TOOLS = frozenset({"save_html_deck", "publish_html_artifact"})
_ARTIFACT_TOOLS = ARTIFACT_TOOLS


def looks_like_html_slides_request(text: str) -> bool:
    return bool(_HTML_SLIDES_RE.search(text or ""))


def _session_meta(task: Task, session: Any | None, session_metadata: dict[str, Any] | None) -> dict[str, Any]:
    meta = dict(session_metadata or {})
    if session is not None:
        meta.update(getattr(session, "metadata", None) or {})
    return meta


def is_html_slides_session(meta: dict[str, Any]) -> bool:
    return str(meta.get("last_intent_class") or "") == "html_slides" or str(
        meta.get("last_skill_name") or ""
    ) == "html_slides"


def extract_slug_from_text(text: str) -> str:
    """Best-effort slug from user reply (e.g. `checkout-redirect-aug-2026`)."""
    match = re.search(r"`([^`]+)`", text or "")
    if match:
        candidate = match.group(1).strip().lower()
        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", candidate):
            return candidate
    for token in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", (text or "").lower()):
        if len(token) >= 4 and "-" in token:
            return token
    return ""


def extract_export_filename_from_text(text: str) -> str:
    """Parse saved deck filename from export paths in user or assistant text."""
    match = _EXPORT_FILENAME_RE.search(text or "")
    if match:
        return match.group(1)
    return ""


def resolve_publish_html_args(
    args: dict[str, Any],
    *,
    task: Task | None = None,
    session_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fill missing publish args from the current task and session metadata."""
    merged = dict(args)
    meta = dict(session_metadata or {})
    text = ""
    if task is not None:
        text = f"{task.cleaned_intent}\n{task.raw_text}".strip()

    if not str(merged.get("slug") or "").strip():
        slug = extract_slug_from_text(text) or str(meta.get("pending_publish_slug") or "").strip()
        if slug:
            merged["slug"] = slug

    if not str(merged.get("source_filename") or "").strip():
        from_text = extract_export_filename_from_text(text)
        from_meta = str(meta.get("last_html_deck_filename") or "").strip()
        if from_text:
            merged["source_filename"] = from_text
        elif from_meta and not str(merged.get("html") or "").strip():
            merged["source_filename"] = from_meta

    return merged


def publish_args_complete(args: dict[str, Any]) -> bool:
    has_html = bool(str(args.get("html") or "").strip())
    has_source = bool(str(args.get("source_filename") or "").strip())
    return has_html or has_source


def looks_like_html_slides_publish_continuation(
    task: Task,
    session: Any | None = None,
    *,
    session_metadata: dict[str, Any] | None = None,
) -> bool:
    """True when user is publishing or confirming a slug for a deck saved this session."""
    text = f"{task.cleaned_intent}\n{task.raw_text}".strip()
    meta = _session_meta(task, session, session_metadata)
    has_saved_deck = bool(str(meta.get("last_html_deck_filename") or "").strip())
    in_slides_session = is_html_slides_session(meta) or has_saved_deck
    if not in_slides_session:
        return False
    if user_wants_publish(text):
        return True
    if extract_slug_from_text(text) and (has_saved_deck or meta.get("pending_publish_slug")):
        return True
    if has_saved_deck and re.search(r"\b(link|url|slug)\b", text, re.I):
        return True
    return False


def looks_like_html_slides_followup(
    task: Task,
    session: Any | None = None,
    *,
    session_metadata: dict[str, Any] | None = None,
) -> bool:
    """True when a short follow-up clearly continues a slide-deck request."""
    text = f"{task.cleaned_intent}\n{task.raw_text}".strip()
    if looks_like_html_slides_request(text):
        return True
    if looks_like_html_slides_publish_continuation(task, session, session_metadata=session_metadata):
        return True
    if not _SLIDES_FOLLOWUP_RE.search(text):
        return False
    meta = _session_meta(task, session, session_metadata)
    if str(meta.get("last_intent_class") or "") == "html_slides":
        return True
    if str(meta.get("last_skill_name") or "") == "html_slides":
        return True
    if session is not None:
        for turn in reversed(getattr(session, "turns", []) or [])[-6:]:
            body = (getattr(turn, "content", None) or "").lower()
            if any(
                token in body
                for token in (
                    "presentation",
                    "slide deck",
                    "html slide",
                    "save_html_deck",
                    "checkout redirect",
                )
            ):
                return True
    lower = text.lower()
    return any(token in lower for token in ("slide", "deck", "presentation"))


def user_wants_publish(text: str) -> bool:
    return bool(_PUBLISH_RE.search(text or ""))


def build_html_slides_tool_plan(
    task: Task,
    *,
    skill_allowed: list[str] | None = None,
    session: Any | None = None,
    session_metadata: dict[str, Any] | None = None,
) -> ToolPlan | None:
    """Deterministic plan — preferred over LLM planner for slide generation."""
    text = f"{task.cleaned_intent}\n{task.raw_text}".strip()
    meta = _session_meta(task, session, session_metadata)
    slides_intent = (
        looks_like_html_slides_request(text)
        or looks_like_html_slides_followup(task, session, session_metadata=session_metadata)
        or looks_like_html_slides_publish_continuation(task, session, session_metadata=session_metadata)
    )
    slug = extract_slug_from_text(text) or str(meta.get("pending_publish_slug") or "").strip()
    saved_filename = str(meta.get("last_html_deck_filename") or "").strip()
    if not saved_filename:
        saved_filename = extract_export_filename_from_text(text)
    publish_intent = (
        user_wants_publish(text)
        or looks_like_html_slides_publish_continuation(
            task, session, session_metadata=session_metadata
        )
        or (bool(slug) and slides_intent and not saved_filename)
    )
    allowed = set(skill_allowed or [])
    if allowed and "save_html_deck" not in allowed and not publish_intent:
        return None
    if allowed and not (allowed <= ARTIFACT_TOOLS or slides_intent or publish_intent):
        return None
    if not allowed and not slides_intent and not publish_intent:
        return None

    if publish_intent and saved_filename:
        use_slug = slug or str(meta.get("pending_publish_slug") or "").strip()
        args_hint: dict[str, Any] = {"source_filename": saved_filename}
        if use_slug:
            args_hint["slug"] = use_slug
        goal = (
            f"Publish saved HTML deck as /artifacts/s/{use_slug}"
            if use_slug
            else "Publish saved HTML deck to /artifacts/sha/{sha256}"
        )
        return ToolPlan(
            goal=goal,
            confidence=0.98,
            tools_needed=["publish_html_artifact"],
            steps=[
                ToolPlanStep(
                    "publish_html_artifact",
                    "publish saved deck",
                    args_hint,
                )
            ],
            intent_class="html_slides",
            strategy="rules",
        )

    tools = ["save_html_deck"]
    steps = [ToolPlanStep("save_html_deck", "save self-contained HTML deck to exports")]
    if publish_intent and (not allowed or "publish_html_artifact" in allowed):
        tools.append("publish_html_artifact")
        steps.append(
            ToolPlanStep(
                "publish_html_artifact",
                "publish deck when user asked for a URL",
                {"slug": slug} if slug else {},
            )
        )

    if publish_intent and "publish_html_artifact" in tools and not slug:
        goal = "Create HTML slide deck, then publish when slug is provided"
    elif publish_intent and saved_filename and slug:
        goal = f"Publish saved HTML deck as /artifacts/s/{slug}"
    elif publish_intent:
        goal = "Create HTML slide deck and publish to artifact hosting"
    else:
        goal = "Create HTML slide deck from user data and save via save_html_deck"

    return ToolPlan(
        goal=goal,
        confidence=0.97,
        tools_needed=tools,
        steps=steps,
        intent_class="html_slides",
        strategy="rules",
    )


def html_deck_session_metadata_patch(result_data: dict[str, Any]) -> dict[str, Any]:
    filename = str(result_data.get("filename") or "").strip()
    if not filename:
        return {}
    return {
        "last_html_deck_filename": filename,
        "last_html_deck_download_url": str(result_data.get("download_url") or ""),
        "last_skill_name": "html_slides",
        "last_intent_class": "html_slides",
    }


def publish_session_metadata_patch(task: Task, *, slug: str = "") -> dict[str, Any]:
    patch: dict[str, Any] = {
        "last_skill_name": "html_slides",
        "last_intent_class": "html_slides",
    }
    text = f"{task.cleaned_intent}\n{task.raw_text}".strip()
    if user_wants_publish(text):
        patch["pending_publish"] = True
    resolved = slug or extract_slug_from_text(text)
    if resolved:
        patch["pending_publish_slug"] = resolved
    return patch


def html_slides_tool_manifest_addendum(
    *,
    publish_requested: bool = False,
    saved_filename: str = "",
) -> str:
    deliver = "publish_html_artifact" if publish_requested else "save_html_deck"
    lines = [
        "\n\n## HTML slides — tool execution required",
        "You have **`save_html_deck`** and **`publish_html_artifact`** this turn.",
    ]
    if publish_requested:
        lines.append(
            "User asked to **publish/host/share** — call `publish_html_artifact` with either:\n"
            "- `slug` + `source_filename` (or `html`) for `/artifacts/s/{slug}`, or\n"
            "- `source_filename` (or `html`) only for `/artifacts/sha/{sha256}`."
        )
        if saved_filename:
            lines.append(
                f"Saved deck file: `{saved_filename}` — pass as `source_filename` to avoid regenerating HTML."
            )
    else:
        lines.append(
            "Default: build HTML, call `save_html_deck`. "
            "Use `publish_html_artifact` only when the user asked for a public URL."
        )
    lines.extend(
        [
            f"Primary action this turn: **`{deliver}`**.",
            "**Do not** claim publish/save succeeded unless the tool returns success.",
        ]
    )
    return "\n".join(lines) + "\n"


def html_slides_system_addendum(
    task: Task,
    *,
    session: Any | None = None,
    config: Any | None = None,
    data_dir: Any | None = None,
) -> str:
    user_id = (task.user_id or "").strip()
    names = (task.metadata or {}).get("slack_user_names") or {}
    display = str(names.get(user_id) or user_id or "requester")
    source_note = (
        f"- Requester Slack user: `{user_id}` ({display})\n"
        if task.source == "slack" and user_id
        else "- Admin chat requester (downloads from `/api/chat/exports/`).\n"
    )
    meta = _session_meta(task, session, None)
    text = f"{task.cleaned_intent}\n{task.raw_text}".strip()
    publish = user_wants_publish(text) or looks_like_html_slides_publish_continuation(
        task, session
    )
    saved = str(meta.get("last_html_deck_filename") or "").strip()
    slug = extract_slug_from_text(text) or str(meta.get("pending_publish_slug") or "").strip()
    lines = [
        "\n\n## HTML slides delivery (mandatory)",
        source_note.rstrip(),
        "- Tools available: `save_html_deck`, `publish_html_artifact`.",
    ]
    if publish and saved:
        slug_line = (
            f"- Slug: `{slug}` — publish to `/artifacts/s/{slug}`."
            if slug
            else "- No slug yet — publish with `source_filename` only for `/artifacts/sha/{{sha256}}`, or ask for a slug."
        )
        lines.extend(
            [
                f"- Saved deck: `{saved}` — publish with `publish_html_artifact` using `source_filename={saved!r}`.",
                slug_line,
                "- Do **not** say publish is unavailable — you have `publish_html_artifact`.",
            ]
        )
    elif publish:
        lines.extend(
            [
                "- User asked to publish — build HTML, call `save_html_deck`, then `publish_html_artifact`.",
                "- Prefer `source_filename` from save; include `slug` when provided for `/artifacts/s/{slug}`.",
            ]
        )
        if slug:
            lines.append(f"- Slug: `{slug}` — publish tool must succeed before citing `/artifacts/s/{slug}`.")
    else:
        lines.extend(
            [
                "- Build the full single-file HTML deck first (embedded CSS/JS, data-URI images).",
                "- **Always** finish by calling `save_html_deck` with the complete HTML.",
                "- Only call `publish_html_artifact` when the user explicitly asks to publish/host/share.",
            ]
        )
    lines.extend(
        [
            "- When publishing from Slack, omit `uploaded_by` / `owner_key` (auto-filled).",
            "- Your final message must cite the tool result (download path or share URL).",
            "- Never say the deck is ready without a successful tool call.",
        ]
    )
    if config is not None:
        from backend.artifacts.slide_branding import (
            build_slide_branding_context,
            html_slides_branding_prompt,
        )

        branding_ctx = build_slide_branding_context(config, data_dir)
        if branding_ctx is not None:
            lines.append(html_slides_branding_prompt(branding_ctx).rstrip())
    return "\n".join(lines) + "\n"


def inject_html_slides_bootstrap_message(
    messages: list[Message],
    task: Task,
    *,
    session: Any | None = None,
) -> list[Message]:
    """Inject mandatory delivery contract before the agent loop (like doc Q&A bootstrap)."""
    text = f"{task.cleaned_intent}\n{task.raw_text}".strip()
    meta = _session_meta(task, session, None)
    publish = user_wants_publish(text) or looks_like_html_slides_publish_continuation(task, session)
    saved = str(meta.get("last_html_deck_filename") or "").strip()
    slug = extract_slug_from_text(text) or str(meta.get("pending_publish_slug") or "").strip()
    if publish and saved and slug:
        block = (
            "## HTML slides publish (execute now)\n"
            f"Publish the saved deck `{saved}` to slug `{slug}`.\n"
            f"Call `publish_html_artifact` with slug=`{slug}` and source_filename=`{saved}`.\n"
            "Do not say the publish tool is unavailable.\n"
        )
    elif publish and saved:
        block = (
            "## HTML slides publish (execute now)\n"
            f"Publish the saved deck `{saved}`.\n"
            f"Call `publish_html_artifact` with source_filename=`{saved}` only "
            "(immutable `/artifacts/sha/{{sha256}}`), or include slug=`...` for `/artifacts/s/{{slug}}`.\n"
            "Do not regenerate HTML or say publish is unavailable.\n"
        )
    elif publish:
        block = (
            "## HTML slides publish\n"
            "User asked for a public URL. Build/save HTML if needed, then call `publish_html_artifact`.\n"
        )
    elif slug:
        block = (
            "## HTML slides (save + publish)\n"
            f"User request: {text[:500]}\n\n"
            f"Requested slug: `{slug}`.\n\n"
            "Required workflow:\n"
            "1. Parse metrics/data from the user message.\n"
            "2. Generate the complete HTML deck (template CSS/JS embedded).\n"
            "3. Call `save_html_deck` with the full HTML string.\n"
            f"4. Call `publish_html_artifact` with slug=`{slug}` and `source_filename` from step 3.\n"
            "5. Reply with the share URL from the publish tool result only — do not invent URLs.\n"
        )
    else:
        block = (
            "## HTML slides preflight (read before acting)\n"
            f"User request: {text[:500]}\n\n"
            "Required workflow:\n"
            "1. Parse metrics/data from the user message.\n"
            "2. Generate the complete HTML deck (template CSS/JS embedded).\n"
            "3. **Call `save_html_deck`** with the full HTML string.\n"
            "4. Reply briefly with the tool result download path.\n"
        )
    out = list(messages)
    if out and out[-1].role == "user":
        out.insert(-1, Message(role="user", content=block))
    else:
        out.append(Message(role="user", content=block))
    return out


def artifact_tools_called(registry: Any) -> bool:
    for entry in getattr(registry, "tool_trace", []) or []:
        if not entry.get("success"):
            continue
        if str(entry.get("tool") or "") in _ARTIFACT_TOOLS:
            return True
    last = getattr(registry, "last_result", None)
    if last is not None and getattr(last, "kind", "") in ("html_deck_saved", "html_artifact_published"):
        return True
    return False


def salvage_html_deck_from_prose(
    prose: str,
    registry: Any,
    *,
    allowed_tools: list[str],
) -> ToolResult | None:
    """Save inline HTML to exports when the model skipped save_html_deck."""
    if artifact_tools_called(registry):
        return None
    deck = extract_html_deck(prose)
    if deck is None:
        return None
    html, filename = deck
    return registry.run(
        "save_html_deck",
        {"html": html, "filename": filename},
        allowed=allowed_tools,
    )


def last_successful_artifact_result(registry: Any) -> ToolResult | None:
    """Most recent successful save/publish from the agent tool trace."""
    import json

    for entry in reversed(getattr(registry, "tool_trace", []) or []):
        if not entry.get("success"):
            continue
        if str(entry.get("tool") or "") not in _ARTIFACT_TOOLS:
            continue
        try:
            payload = json.loads(str(entry.get("observation") or ""))
        except json.JSONDecodeError:
            continue
        kind = str(payload.get("kind") or entry.get("result_kind") or "")
        if kind in ("html_deck_saved", "html_artifact_published"):
            return ToolResult(kind=kind, data=dict(payload.get("data") or {}))
    last = getattr(registry, "last_result", None)
    if last is not None and getattr(last, "kind", "") in ("html_deck_saved", "html_artifact_published"):
        return last
    return None


def format_artifact_tool_reply(
    result: ToolResult,
    *,
    task: Task | None = None,
    public_base_url: str = "",
) -> str:
    from backend.artifacts.formatting import (
        format_published_artifact_slack,
        format_published_artifact_ui,
        format_saved_html_deck_slack,
        format_saved_html_deck_ui,
    )

    slack = task is not None and task.source == "slack"
    if result.kind == "html_deck_saved":
        formatter = format_saved_html_deck_slack if slack else format_saved_html_deck_ui
        return formatter(result.data, public_base_url=public_base_url)
    if result.kind == "html_artifact_published":
        formatter = format_published_artifact_slack if slack else format_published_artifact_ui
        return formatter(result.data, public_base_url=public_base_url)
    return ""


def resolve_html_slides_reply(
    registry: Any,
    *,
    task: Task | None = None,
    public_base_url: str = "",
) -> tuple[str, ToolResult | None, dict[str, Any] | None]:
    """Prefer verified artifact tool output over model prose."""
    result = last_successful_artifact_result(registry)
    if result is None:
        return "", None, None
    reply = format_artifact_tool_reply(result, task=task, public_base_url=public_base_url)
    patch = None
    if result.kind == "html_deck_saved":
        patch = html_deck_session_metadata_patch(result.data)
    elif result.kind == "html_artifact_published":
        patch = {
            "pending_publish": False,
            "last_published_slug": str(result.data.get("slug") or ""),
            "last_published_url": str(result.data.get("share_url") or result.data.get("slug_url") or ""),
        }
    return reply, result, patch
