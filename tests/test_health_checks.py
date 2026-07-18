"""Health check registry and integration test helpers."""

from __future__ import annotations

from backend.health import (
    INTEGRATION_HEALTH_CHECKS,
    run_all_checks,
    run_integration_check,
)
from backend.models.config import AlfredConfig


def test_run_all_checks_includes_web_search():
    checks = run_all_checks(AlfredConfig())
    assert "web_search" in checks
    assert checks["web_search"]["skipped"] is True


def test_run_all_checks_expected_keys():
    checks = run_all_checks(AlfredConfig())
    assert set(checks.keys()) == {
        "slack",
        "git",
        "aws",
        "jira",
        "google",
        "web_search",
        "ai",
    }


def test_integration_health_checks_registry():
    assert INTEGRATION_HEALTH_CHECKS == frozenset(
        {"slack", "git", "aws", "jira", "google", "web_search"},
    )


def test_run_integration_check_unknown_raises():
    try:
        run_integration_check("unknown", AlfredConfig())
    except ValueError as exc:
        assert "unknown" in str(exc).lower()
    else:
        raise AssertionError("expected ValueError")
