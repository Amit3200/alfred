---
name: investigate_bug
description: Analyze bugs from Slack threads using git and logs
mode: investigation
trigger_keywords: ["bug", "wrong", "broken", "error", "why", "issue"]
allowed_channels: ["*"]
allowed_tools:
  - git_log
  - git_blame
  - grep_repo
  - read_file
  - slack_reply
requires_thread_context: true
---

# Objective

Analyze the bug described in the Slack thread. Use git history and code search to identify the root cause.

# Governance Rules

- READ-ONLY: Do not modify any code or infrastructure.
- Always cite file paths and line numbers when referencing code.
