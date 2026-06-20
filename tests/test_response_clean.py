"""Tests for response scaffold cleanup."""

from backend.ingress.response_clean import clean_response_scaffold


def test_strips_scaffold_labels():
    raw = "Lead line: Hello team.\n\nBody:\n\n*Summary*\nSome facts.\n\nNext Steps:\n1. Do thing"
    cleaned = clean_response_scaffold(raw)
    assert "Lead line:" not in cleaned
    assert "Body:" not in cleaned
    assert "Next Steps:" not in cleaned
    assert "Hello team." in cleaned
    assert "*Summary*" in cleaned
