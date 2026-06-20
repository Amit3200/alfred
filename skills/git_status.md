---
name: git_status
description: List and inspect pull requests via GitHub or GitLab API
mode: investigation
trigger_keywords:
  - pr
  - pull request
  - merge request
  - my prs
  - open prs
  - my pull requests
allowed_channels:
  - "*"
allowed_tools:
  - list_my_prs
  - list_prs
  - get_pr
  - list_repos
requires_thread_context: false
---

# Objective

Answer questions about pull requests and repositories using Git API tools.
Do not guess — call the appropriate tool first.

# Execution steps

1. For "my PRs" or "my open pull requests" → call `list_my_prs`.
2. For PRs on a specific repo → call `list_prs` with `owner/name`.
3. For one PR by number → call `get_pr` with repo and number.
4. If the repo is unclear, call `list_repos` or ask which repository.

# Response format

When tool data is returned, keep replies *short*:

```
*4 open PRs*

`cipher`
• <https://github.com/org/cipher/pull/1685|#1685 Thanks page>

`flexype-adhocs`
• <https://github.com/org/flexype-adhocs/pull/91|#91 SQS Consumer Support Added>
```

- Group by repo short name. One bullet per PR with inline Slack link.
- Do not put the URL on a separate line. Do not repeat "There is an open PR titled…" per item.

# Governance

- READ-ONLY — never merge, close, or modify PRs.
- Only report data returned by tools.
