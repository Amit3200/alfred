"""Tests for deterministic PR overview and hallucination guard."""

from backend.ingress.pr_analysis import (
    _is_grounded_response,
    _prioritize_files,
    build_deterministic_pr_overview,
)


def test_prioritize_files_puts_added_first():
    files = [
        {"filename": "hooks/util.py", "status": "modified", "additions": 5, "deletions": 3},
        {"filename": "sqs_consumer.py", "status": "added", "additions": 200, "deletions": 0},
    ]
    ordered = _prioritize_files(files)
    assert ordered[0]["filename"] == "sqs_consumer.py"


def test_deterministic_overview_uses_pr_body():
    detail = {
        "number": 91,
        "title": "Feat: SQS Consumer Support Added",
        "repo": "FlexyPe/flexype-adhocs",
        "url": "https://github.com/FlexyPe/flexype-adhocs/pull/91",
        "head": "feature/sqs",
        "base": "main",
        "author": "amit",
        "body": "Add AWS SQS support alongside existing RabbitMQ consumers for migration.",
    }
    files = [
        {"filename": "sqs_consumer.py", "status": "added", "additions": 213, "deletions": 0},
        {"filename": "adhoc_consumer.py", "status": "modified", "additions": 10, "deletions": 5},
    ]
    text = build_deterministic_pr_overview(detail, files)
    assert "SQS Consumer Support" in text
    assert "sqs_consumer.py" in text
    assert "RabbitMQ" in text
    assert "Magento" not in text


def test_grounding_rejects_magento_hallucination():
    detail = {"title": "SQS Consumer Support", "repo": "FlexyPe/flexype-adhocs"}
    files = [{"filename": "sqs_consumer.py", "status": "added", "additions": 100, "deletions": 0}]
    bad = "The code appears to be Magento 2 Integration with RESTful APIs and PEP 8 naming."
    assert not _is_grounded_response(bad, detail, files)


def test_grounding_accepts_specific_file_reference():
    detail = {"title": "SQS Consumer Support", "repo": "FlexyPe/flexype-adhocs"}
    files = [{"filename": "katarot/consumer/dev/sqs_consumer.py", "status": "added", "additions": 100, "deletions": 0}]
    good = "In `sqs_consumer.py`, messages are deleted after processing regardless of outcome."
    assert _is_grounded_response(good, detail, files)
