"""Slack-facing formatters for HTML artifact tool results."""

from __future__ import annotations

from backend.artifacts.urls import artifact_public_url


def format_published_artifact_slack(data: dict, *, public_base_url: str = "") -> str:
    slug = str(data.get("slug") or "").strip()
    title = str(data.get("title") or "").strip()
    sha256 = str(data.get("sha256") or "").strip()
    publish_mode = str(data.get("publish_mode") or ("slug" if slug else "sha"))
    slug_path = str(data.get("slug_url") or (f"/artifacts/s/{slug}" if slug else ""))
    sha_path = str(data.get("sha_url") or (f"/artifacts/sha/{sha256}" if sha256 else ""))
    if publish_mode == "sha" or not slug:
        primary_path = sha_path
        primary_label = "Share (immutable)"
    else:
        primary_path = slug_path
        primary_label = "Share"
    share_url = str(data.get("share_url") or artifact_public_url(public_base_url, primary_path))
    uploaded_by = str(data.get("uploaded_by") or "")
    source = str(data.get("source") or "")
    lines = ["*Published HTML slides*"]
    if title:
        lines.append(f"*{title}*")
    lines.append(f"{primary_label}: {share_url}")
    if slug and sha_path and publish_mode == "slug":
        lines.append(f"Immutable copy: {artifact_public_url(public_base_url, sha_path)}")
    if uploaded_by:
        via = "via Slack" if source == "slack" else f"by {uploaded_by}"
        lines.append(f"Uploaded {via}")
    if slug:
        lines.append("_Re-publish the same slug to update; this link always serves the latest version._")
    else:
        lines.append("_Content-addressed link — same HTML always resolves to this URL._")
    return "\n".join(lines)


def format_saved_html_deck_slack(data: dict, *, public_base_url: str = "") -> str:
    filename = str(data.get("filename") or "presentation.html")
    download = str(data.get("download_url") or "")
    if download and public_base_url:
        download = artifact_public_url(public_base_url, download)
    lines = [
        "*HTML slide deck saved* (not published to a share URL).",
        f"File: `{filename}`",
    ]
    if download:
        lines.append(f"Download: {download}")
    lines.append("Ask me to *publish* with a slug when you want a link like `/artifacts/s/your-deck`.")
    return "\n".join(lines)


def format_saved_html_deck_ui(data: dict, *, public_base_url: str = "") -> str:
    filename = str(data.get("filename") or "presentation.html")
    download = str(data.get("download_url") or "")
    if download:
        download = artifact_public_url(public_base_url, download)
    lines = [
        "**HTML slide deck saved**",
        f"File: `{filename}`",
    ]
    if download:
        lines.append(f"Download: {download}")
    lines.append(
        "Not published yet — ask to publish with a slug when you want a link like `/artifacts/s/your-deck`."
    )
    return "\n".join(lines)


def format_published_artifact_ui(data: dict, *, public_base_url: str = "") -> str:
    slug = str(data.get("slug") or "").strip()
    title = str(data.get("title") or "").strip()
    sha256 = str(data.get("sha256") or "").strip()
    publish_mode = str(data.get("publish_mode") or ("slug" if slug else "sha"))
    slug_path = str(data.get("slug_url") or (f"/artifacts/s/{slug}" if slug else ""))
    sha_path = str(data.get("sha_url") or (f"/artifacts/sha/{sha256}" if sha256 else ""))
    if publish_mode == "sha" or not slug:
        primary_path = sha_path
        primary_label = "Share link (immutable)"
    else:
        primary_path = slug_path
        primary_label = "Share link"
    share_url = str(data.get("share_url") or artifact_public_url(public_base_url, primary_path))
    lines = ["**Published HTML slides**"]
    if title:
        lines.append(f"**{title}**")
    lines.append(f"{primary_label}: {share_url}")
    if slug and sha_path and publish_mode == "slug":
        lines.append(f"Immutable copy: {artifact_public_url(public_base_url, sha_path)}")
    if slug:
        lines.append("Re-upload the same slug to update; this link always serves the latest version.")
    else:
        lines.append("Content-addressed link — same HTML always resolves to this URL.")
    return "\n".join(lines)
