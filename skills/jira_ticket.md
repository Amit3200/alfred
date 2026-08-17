---
name: jira_ticket
description: List, inspect, and update JIRA tickets; link issues to GitHub PRs
mode: investigation
trigger_keywords:
  - link ticket
  - link issue
  - link jira
  - link pr to
  - attach pr
allowed_channels:
  - "*"
allowed_tools:
  - get_jira_issue
  - link_jira_issue
  - jira_search
  - transition_jira_issue
  - jira_add_comment
  - jira_assign_issue
requires_thread_context: true
---

# Objective

Help users manage JIRA tickets — read status, list work, change status, comment, and link PRs.

# Execution steps

1. For a specific key (`ENG-123`, URL, or "status of …") → `get_jira_issue`.
2. For lists ("my open tickets", "bugs in ENG") → `list_jira_issues` with project/status/JQL.
3. When the user asks to **move**, **transition**, or **change status** → `transition_jira_issue`.
4. When the user asks to **comment** → `add_jira_comment`.
5. When a PR URL and ticket appear together, or user asks to link → `link_jira_issue`.
6. Default project comes from config when omitted.

# Response format

- Lead with status or count in one sentence.
- Include the JIRA browse URL.
- For writes, confirm what changed (old→new status, link added, etc.).

# Governance

- **Read** anytime the user asks about tickets.
- **Write** (transition, comment, link) only when the user explicitly requests it — never auto-close or auto-transition.
- Respect `allowed_projects` in config — do not touch other projects.
- Linking PRs is preferred over duplicating ticket text in comments.

# Future

Alfred will use ticket descriptions to open pull requests — gather acceptance criteria and linked repos from the issue before coding.
