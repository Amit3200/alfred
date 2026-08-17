"""Tests for AWS error formatting."""

from __future__ import annotations

from botocore.exceptions import ClientError

from backend.integrations.aws.errors import wrap_aws_error


def _client_error(code: str, message: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": message}}, "TestOperation")


def test_wrap_access_denied():
    exc = wrap_aws_error(
        _client_error("AccessDenied", "User is not authorized"),
        action="StartQuery",
        service="cloudwatch",
    )
    assert isinstance(exc, RuntimeError)
    assert "permission denied" in str(exc).lower()
    assert "StartQuery" in str(exc)
    assert "cloudwatch" in str(exc)


def test_wrap_not_found():
    exc = wrap_aws_error(
        _client_error("ResourceNotFoundException", "Log group missing"),
        action="StartQuery",
        service="cloudwatch",
    )
    assert "not found" in str(exc).lower()
