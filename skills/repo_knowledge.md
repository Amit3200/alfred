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
  - playbook
  - readme
  - architecture doc
allowed_channels:
  - "*"
allowed_tools:
  - search_repo_docs
  - read_repo_doc
  - list_repo_docs
  - grep_repo
  - read_file
  - query_graph
requires_thread_context: false
---

# Objective

Answer questions about repository documentation, runbooks, and internal playbooks using **only** indexed doc search results.

# Rules

1. Always call `search_repo_docs` before answering documentation questions.
2. Cite the doc path for every claim (e.g. `docs/runbooks/redirect.md`).
3. If search returns no results, say explicitly that nothing was found — do not guess from training data.
4. Use `read_repo_doc` for full context when a search hit is relevant but excerpt is incomplete.
5. Never invent URLs, file paths, or procedures not present in tool results.

# Workflow

1. `search_repo_docs` with the user's question as query.
2. If hits found → synthesize answer with citations; optionally `read_repo_doc` for detail.
3. If no hits → `list_repo_docs` to suggest available docs, or state "not found in indexed documentation."
