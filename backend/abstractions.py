"""Abstract base classes for Alfred subsystems."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterator


class BaseQueue(ABC):
    @abstractmethod
    def push(self, task: dict[str, Any]) -> str: ...

    @abstractmethod
    def pop(self) -> dict[str, Any] | None: ...

    @abstractmethod
    def ack(self, task_id: str) -> None: ...


class StorageProvider(ABC):
    @abstractmethod
    def get_session(self, key: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def save_session(self, key: str, session: dict[str, Any]) -> None: ...

    @abstractmethod
    def log_audit(self, entry: dict[str, Any]) -> None: ...


class IndexProvider(ABC):
    @abstractmethod
    def match_skill(self, query: str, skills: list[dict[str, Any]]) -> dict[str, Any] | None: ...


class IngressHandler(ABC):
    @abstractmethod
    def parse(self, raw_event: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def ack(self, raw_event: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def reply(self, task: dict[str, Any], message: str) -> None: ...
