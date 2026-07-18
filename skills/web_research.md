---
name: web_research
description: Search the public web for docs, errors, release notes, and external context
mode: investigation
trigger_keywords:
  - search the web
  - web search
  - google for
  - look up online
  - latest version
  - release notes
  - documentation for
  - search online
  - internet search
allowed_channels:
  - "*"
allowed_tools:
  - web_search
requires_thread_context: false
---

# Objective

Answer questions that require **external** knowledge — library docs, CVEs, SaaS behavior, error messages from third-party services, or “what’s the latest version of X”.

Do **not** use this skill when the answer should come from your mirrored repos, JIRA, or AWS logs.

# Execution steps

1. Form a precise `web_search` query (include product name, version, or exact error text when known).
2. Summarize findings in plain language — cite titles and URLs from results.
3. If results conflict or are thin, say so and suggest a narrower follow-up query.

# Response format

- One-sentence takeaway first.
- Bullet list of key findings with linked sources.
- Note when information may be stale (check result dates if mentioned).

# Governance

- READ-ONLY — never attempt to log in, post, or scrape authenticated pages.
- Do not treat web snippets as private company data; cross-check with internal repos when the question is about *your* code.
- Prefer official docs and vendor sites over random forums when both appear.
