---
name: investigate_bug
description: Search and read code in mirrored repositories to answer where/how questions
mode: investigation
trigger_keywords:
  - where is
  - where does
  - how is
  - how does
  - what does
  - what do
  - find in code
  - grep
  - stack trace
  - investigate
  - duplicate order
  - handled in
  - which file
  - explain
  - tell me what
  - tell me about
  - what are the steps
  - steps of
  - walk me through
  - can you tell
allowed_channels:
  - "*"
allowed_tools:
  - query_graph
  - grep_repo
  - read_file
  - git_log
  - git_blame
  - git_show
  - get_pr
  - list_repos
  - cloudwatch_query
  - list_cloudwatch_log_groups
  - athena_query
  - web_search
requires_thread_context: true
---

# Objective

Investigate code in configured Git repositories using local mirror tools.
Each Slack thread or UI chat has its **own mirror workspace** — do not assume another conversation's checkout.

# Execution steps

1. Identify the repository from the question, thread context, or `list_repos`.
2. When Graphify is enabled, use `query_graph` first for structure, callers, and blast radius.
3. Use `grep_repo` to locate symbols, error strings, or paths.
4. Use `read_file` for surrounding context (cite `path:line`).
5. Pass `ref` when investigating a PR branch (use `head` from `get_pr`) or a named branch.
6. Use `git_log` / `git_blame` / `git_show` when history or authorship matters.
7. When the question involves production errors or runtime behavior, use `cloudwatch_query` (by `service_name` or `log_group`) or `athena_query` for dataset lookups.

# Response format

- Lead with the answer in one sentence.
- Cite findings as `` `path/to/file.py:42` `` with a short explanation.
- Keep tool JSON out of the user-visible reply — the system renders structured results.

# Governance

- READ-ONLY — never commit, push, or modify repositories.
- Only search repos in the configured allowlist.
