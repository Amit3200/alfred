"""Shared prompts for documentation Q&A worker mode."""

from __future__ import annotations


def doc_qa_system_addendum() -> str:
    return (
        "\n\n## Documentation Q&A mode (active)\n"
        "1. Call `search_repo_docs` first with the user's question.\n"
        "2. If a hit matches the asked product/integration, call `read_repo_doc` for full content.\n"
        "3. Start your final answer with **Yes** or **No**.\n"
        "4. If search returns no relevant hits, answer **No** — never substitute another product's doc.\n"
        "5. Always include the public documentation URL from the tool result `url` field. "
        "For FlexyPe/docs that is https://docs.flexype.io/{path without .md/.mdx}. "
        "Example: getting-started/introduction.mdx → https://docs.flexype.io/getting-started/introduction "
        "and platforms/hydrogen.mdx → https://docs.flexype.io/platforms/hydrogen.\n"
        "6. Put that clickable URL in the Slack reply. Do not cite only a repo path like `platforms/hydrogen.mdx`.\n"
        "7. Do not paste example checkout URLs or `{placeholder}` merchant links unless the user asked for a checkout link."
    )
