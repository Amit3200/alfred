"""Periskope REST client (WhatsApp groups, tickets, tasks, messages)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import requests

from backend.models.config import AlfredConfig, PeriskopeConfig

DEFAULT_BASE_URL = "https://api.periskope.app/v1"
_PHONE_ID_RE = re.compile(r"^phone-[a-z0-9]+$", re.I)


class PeriskopeApiError(RuntimeError):
    pass


class PeriskopeApiClient:
    def __init__(
        self,
        *,
        api_token: str,
        org_phone: str = "",
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 20,
    ) -> None:
        self.api_token = (api_token or "").strip()
        self.org_phone = _normalize_org_phone(org_phone)
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        if not self.api_token:
            raise PeriskopeApiError("Periskope API token is not configured.")

    @classmethod
    def from_alfred_config(cls, config: AlfredConfig) -> PeriskopeApiClient:
        settings = _periskope_settings(config)
        return cls(
            api_token=str(getattr(settings, "api_token", "") or ""),
            org_phone=str(getattr(settings, "org_phone", "") or ""),
            base_url=str(getattr(settings, "base_url", "") or DEFAULT_BASE_URL),
        )

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.org_phone:
            headers["x-phone"] = self.org_phone
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> Any:
        url = f"{self.base_url}{path if path.startswith('/') else '/' + path}"
        response = requests.request(
            method,
            url,
            headers=self._headers(),
            params=params,
            json=json_body,
            timeout=timeout if timeout is not None else self.timeout,
        )
        if response.status_code == 401:
            raise PeriskopeApiError("Periskope authentication failed — check API token and x-phone.")
        if response.status_code == 429:
            raise PeriskopeApiError("Periskope rate limit exceeded. Retry shortly.")
        if response.status_code >= 400:
            detail = response.text[:300]
            raise PeriskopeApiError(f"Periskope API {response.status_code}: {detail}")
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise PeriskopeApiError("Periskope returned non-JSON.") from exc

    def ping(self) -> dict[str, Any]:
        data = self.request("GET", "/phones")
        if isinstance(data, dict):
            return data
        return {"phones": data}

    def list_chats(self, *, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        return self.request("GET", "/chats", params={"offset": offset, "limit": limit})

    def list_messages(
        self,
        *,
        chat_id: str = "",
        start_time: str = "",
        end_time: str = "",
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Fetch messages.

        Date filters (``start_time`` / ``end_time``) exist only on
        ``GET /chats/messages``. Per-chat ``GET /chats/{chat_id}/messages``
        supports offset/limit only — when a window is set we use the org-wide
        endpoint and filter by ``chat_id`` in the connector.
        """
        params: dict[str, Any] = {"offset": offset, "limit": max(1, min(int(limit or 100), 2000))}
        windowed = bool(start_time or end_time)
        if windowed:
            if start_time:
                params["start_time"] = start_time
            if end_time:
                params["end_time"] = end_time
            return self.request("GET", "/chats/messages", params=params, timeout=45)
        if chat_id:
            encoded = quote(chat_id, safe="@.")
            return self.request("GET", f"/chats/{encoded}/messages", params=params, timeout=45)
        return self.request("GET", "/chats/messages", params=params, timeout=45)

    def list_tickets(self, *, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        return self.request("GET", "/tickets", params={"offset": offset, "limit": limit})

    def get_ticket(self, ticket_id: str) -> dict[str, Any]:
        return self.request("GET", f"/tickets/{ticket_id}")

    def list_tasks(self, *, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        return self.request("GET", "/tasks", params={"offset": offset, "limit": limit})


def _normalize_org_phone(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if _PHONE_ID_RE.match(value):
        return value
    if "@" in value:
        value = value.split("@", 1)[0]
    return re.sub(r"\D", "", value)


def _periskope_settings(config: AlfredConfig) -> PeriskopeConfig:
    connectors = getattr(config, "connectors", None)
    settings = getattr(connectors, "periskope", None) if connectors is not None else None
    if settings is None:
        return PeriskopeConfig()
    return settings
