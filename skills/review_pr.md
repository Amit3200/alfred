---
name: review_pr
description: Review pull requests using diffs and local branch checkout
mode: investigation
trigger_keywords:
  - review pr
  - review this pr
  - code review
  - what does this pr
  - what does the pr
  - explain this pr
  - understand this pr
  - what changed in
  - walk me through
  - walk through this pr
  - analyze this pr
  - investigate this pr
  - navigate the code
  - what it does
allowed_channels:
  - "*"
allowed_tools:
  - get_pr
  - get_pr_changes
  - grep_repo
  - read_file
  - git_log
  - git_blame
  - list_repos
requires_thread_context: false
---

# Objective

Review or explain a pull request using **real code changes** — not just the PR description.

# Execution steps

1. If the user gives a PR URL or `#number`, call `get_pr` then `get_pr_changes`.
2. Note the `head` branch from `get_pr` — pass it as `ref` to `grep_repo`, `read_file`, etc.
3. Read changed files for context when diffs are truncated or unclear.
4. Summarize what the PR does, how the main flow works, and any review concerns.

# Response format

- **Summary** — what the PR does (2–3 sentences).
- **Key changes** — bullets with `` `path/to/file` `` citations.
- **How it works** — main behavior or flow.
- **Review notes** — risks, missing tests, or open questions (if any).

# Governance

- READ-ONLY — never merge, close, or modify PRs or repos.
- Cite file paths from tool results; do not invent changes.
