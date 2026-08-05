"""Shared prompts for documentation Q&A worker mode."""

from __future__ import annotations


def doc_qa_system_addendum() -> str:
    return (
        "\n\n## Documentation Q&A mode (active)\n"
        "1. Call `search_repo_docs` first with the user's question.\n"
        "2. If a hit matches the asked product/integration, call `read_repo_doc` for full content.\n"
        "3. Start your final answer with **Yes** or **No**.\n"
        "4. If search returns no relevant hits, answer **No** — never substitute another product's doc.\n"
        "5. Cite only doc paths that appear in tool results.\n"
        "6. Do not paste example checkout URLs or `{placeholder}` links unless the user asked for a link."
    )
