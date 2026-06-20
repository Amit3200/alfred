"""Tests for UI Markdown formatting."""

from backend.ingress.ui_format import format_for_ui

_LEGACY_PR_LIST = """*4 open PRs*

`cipher`
• #1685 Add Thankyou page — https://github.com/FlexyPe/cipher/pull/1685

`flexype-adhocs`
• #91 Feat: SQS Consumer Support Added — https://github.com/FlexyPe/flexype-adhocs/pull/91 • #16 Fix tests — https://github.com/FlexyPe/flexype-adhocs/pull/16 • #8 Dump PR — https://github.com/FlexyPe/flexype-adhocs/pull/8"""


def test_slack_links_to_markdown():
    text = format_for_ui("See <https://github.com/o/r/pull/1|#1 Fix bug>")
    assert text == "See [#1 Fix bug](https://github.com/o/r/pull/1)"


def test_slack_bold_to_markdown():
    text = format_for_ui("*4 open PRs*")
    assert text == "**4 open PRs**"


def test_preserves_code_fences():
    text = format_for_ui("*bold*\n```\n*not bold*\n```")
    assert "**bold**" in text
    assert "*not bold*" in text


def test_legacy_pr_list_normalization():
    text = format_for_ui(_LEGACY_PR_LIST)
    assert "**4 open PRs**" in text
    assert "### cipher" in text
    assert "### flexype-adhocs" in text
    assert "[#1685 Add Thankyou page](https://github.com/FlexyPe/cipher/pull/1685)" in text
    assert "[#91 Feat: SQS Consumer Support Added](https://github.com/FlexyPe/flexype-adhocs/pull/91)" in text
    assert "[#16 Fix tests](https://github.com/FlexyPe/flexype-adhocs/pull/16)" in text
    assert "[#8 Dump PR](https://github.com/FlexyPe/flexype-adhocs/pull/8)" in text
    assert " — https://" not in text
