---
name: repo_knowledge
description: Search and read repository documentation, runbooks, and playbooks with cited excerpts.
mode: investigation
trigger_keywords:
  - runbook
  - documentation
  - docs say
  - what does our
  - how do we
  - how can
  - how to
  - configure
  - integration
  - integrate
  - setup
  - playbook
  - readme
  - architecture doc
  - google ads
  - analytics
  - what is
  - what's
  - all about
  - tell me about
  - explain
  - describe
  - upselling
  - feature
allowed_channels:
  - "*"
allowed_tools:
  - search_repo_docs
  - read_repo_doc
  - list_repo_docs
  - web_search
  - grep_repo
  - read_file
  - query_graph
requires_thread_context: false
---

# Objective

Answer support and documentation questions using **only** indexed doc search and read results. Prioritize accuracy over speed.

# Rules

1. Always call `search_repo_docs` **first** — never answer from memory or say you will look later.
2. If a search hit matches the asked product/integration, call `read_repo_doc` before summarizing.
3. Start integration/support answers with **Yes** or **No**, then concise steps or a clear "not documented".
4. If search returns no relevant hit for the asked entity, answer **No** — do not substitute another platform's doc.
5. Cite the doc path for every claim (e.g. `integrations/analytics/google-ads.mdx`).
6. Only use `web_search` when doc search and `list_repo_docs` show nothing relevant.
7. Never invent URLs, file paths, or procedures not present in tool results.

# Workflow

1. `search_repo_docs` with the user's question.
2. If a matching hit → `read_repo_doc` → summarize with citations.
3. If no matching hit → optionally `list_repo_docs` → answer **No**, not documented.
4. Deliver a short summary; do not paste raw MDX/frontmatter.
