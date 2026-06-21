"""AWS error formatting — clear messages for IAM and config failures."""

from __future__ import annotations

from botocore.exceptions import BotoCoreError, ClientError

ACCESS_DENIED_CODES = frozenset(
    {
        "AccessDenied",
        "AccessDeniedException",
        "UnauthorizedOperation",
        "UnauthorizedException",
        "InvalidClientTokenId",
        "ExpiredToken",
        "ExpiredTokenException",
        "SignatureDoesNotMatch",
        "KMSAccessDeniedException",
    }
)

NOT_FOUND_CODES = frozenset(
    {
        "ResourceNotFoundException",
        "LogGroupNotFoundException",
        "InvalidParameterException",
    }
)


def wrap_aws_error(exc: Exception, *, action: str, service: str) -> RuntimeError:
    """Turn botocore errors into user-facing RuntimeError messages."""
    if isinstance(exc, ClientError):
        error = exc.response.get("Error") or {}
        code = str(error.get("Code") or "")
        message = str(error.get("Message") or str(exc))
        if code in ACCESS_DENIED_CODES:
            return RuntimeError(
                f"AWS {service}: permission denied for {action} ({code}). "
                f"Grant the required IAM action or add '{service}' to aws.allowed_services. "
                f"Detail: {message}"
            )
        if code in NOT_FOUND_CODES:
            return RuntimeError(f"AWS {service}: resource not found for {action} ({code}): {message}")
        return RuntimeError(f"AWS {service} {action} failed ({code}): {message}")
    if isinstance(exc, BotoCoreError):
        return RuntimeError(f"AWS {service} connection error during {action}: {exc}")
    if isinstance(exc, (ValueError, RuntimeError)):
        return exc if isinstance(exc, RuntimeError) else RuntimeError(str(exc))
    return RuntimeError(f"AWS {service} {action} failed: {exc}")
