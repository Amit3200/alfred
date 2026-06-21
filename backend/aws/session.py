"""Shared boto3 session and client helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from backend.aws.errors import wrap_aws_error

if TYPE_CHECKING:
    from backend.models.config import AlfredConfig

BOTO_SERVICE_MAP = {
    "cloudwatch": "logs",
    "athena": "athena",
    "sts": "sts",
}


def require_boto3() -> Any:
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 not installed — run: pip install alfred-agent[aws]") from exc
    return boto3


def assert_service_allowed(config: AlfredConfig, service: str) -> None:
    allowed = [item.lower() for item in (config.aws.allowed_services or [])]
    key = service.lower()
    if allowed and key not in allowed:
        raise ValueError(
            f"AWS service '{service}' is not enabled. "
            f"Add '{service}' to aws.allowed_services in config (current: {allowed})."
        )


def aws_session(config: AlfredConfig) -> Any:
    if not config.aws.enabled:
        raise RuntimeError("AWS integration is disabled.")
    boto3 = require_boto3()
    if config.aws.access_key_id and config.aws.secret_access_key:
        return boto3.Session(
            aws_access_key_id=config.aws.access_key_id,
            aws_secret_access_key=config.aws.secret_access_key,
            region_name=config.aws.region,
        )
    return boto3.Session(profile_name=config.aws.profile, region_name=config.aws.region)


def aws_client(config: AlfredConfig, service: str, *, check_allowed: bool = True) -> Any:
    if check_allowed:
        assert_service_allowed(config, service)
    boto_service = BOTO_SERVICE_MAP.get(service.lower(), service.lower())
    return aws_session(config).client(boto_service, region_name=config.aws.region)


def aws_call(config: AlfredConfig, service: str, action: str, fn: Any) -> Any:
    """Run a boto3 call with consistent error wrapping."""
    try:
        return fn()
    except Exception as exc:
        raise wrap_aws_error(exc, action=action, service=service) from exc
