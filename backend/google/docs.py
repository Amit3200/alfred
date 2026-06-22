"""Google Docs read/create/append helpers."""

from __future__ import annotations

from typing import Any

from backend.google.credentials import build_google_credentials, refresh_if_needed


def _docs_service(credentials_json: str, refresh_token: str):
    from googleapiclient.discovery import build

    creds = build_google_credentials(
        credentials_json=credentials_json,
        refresh_token=refresh_token,
    )
    refresh_if_needed(creds)
    return build("docs", "v1", credentials=creds, cache_discovery=False)


def _drive_service(credentials_json: str, refresh_token: str):
    from googleapiclient.discovery import build

    creds = build_google_credentials(
        credentials_json=credentials_json,
        refresh_token=refresh_token,
    )
    refresh_if_needed(creds)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _extract_text(document: dict[str, Any]) -> str:
    parts: list[str] = []
    for element in document.get("body", {}).get("content") or []:
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        for run in paragraph.get("elements") or []:
            text = run.get("textRun", {}).get("content")
            if text:
                parts.append(text)
    return "".join(parts).strip()


def read_doc(
    *,
    document_id: str,
    credentials_json: str,
    refresh_token: str = "",
) -> dict[str, Any]:
    service = _docs_service(credentials_json, refresh_token)
    document = service.documents().get(documentId=document_id).execute()
    return {
        "document_id": document_id,
        "title": document.get("title", ""),
        "text": _extract_text(document),
    }


def create_doc(
    *,
    title: str,
    body_text: str = "",
    credentials_json: str,
    refresh_token: str = "",
) -> dict[str, Any]:
    docs = _docs_service(credentials_json, refresh_token)
    document = docs.documents().create(body={"title": title}).execute()
    document_id = document["documentId"]
    if body_text.strip():
        append_doc(
            document_id=document_id,
            text=body_text,
            credentials_json=credentials_json,
            refresh_token=refresh_token,
        )
    return {
        "document_id": document_id,
        "title": title,
        "url": f"https://docs.google.com/document/d/{document_id}/edit",
    }


def append_doc(
    *,
    document_id: str,
    text: str,
    credentials_json: str,
    refresh_token: str = "",
) -> dict[str, Any]:
    docs = _docs_service(credentials_json, refresh_token)
    document = docs.documents().get(documentId=document_id).execute()
    end_index = document.get("body", {}).get("content", [{}])[-1].get("endIndex", 1)
    insert_index = max(end_index - 1, 1)
    suffix = text if text.endswith("\n") else f"{text}\n"
    requests = [
        {
            "insertText": {
                "location": {"index": insert_index},
                "text": suffix,
            }
        }
    ]
    docs.documents().batchUpdate(documentId=document_id, body={"requests": requests}).execute()
    return {
        "document_id": document_id,
        "appended_chars": len(suffix),
    }
