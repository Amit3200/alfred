---
name: slack_board_management
description: Create and manage tasks on Slack List boards (Kanban) from channel threads.
mode: investigation
trigger_keywords:
  - create task
  - create ticket
  - add task
  - bugs tracker
  - slack board
  - move task
  - assign task
  - list tasks
  - open tasks
allowed_channels:
  - "*"
requires_thread_context: false
allowed_tools:
  - slack_fetch_thread
  - slack_board_create_task
  - slack_board_update_task
  - slack_board_search_tasks
  - slack_board_get_task
  - slack_board_comment
---

# Objective

Manage **Slack List** Kanban boards (e.g. Bugs tracker) from natural language in Slack.
Use the board configured for the current channel — do not create JIRA issues unless the user explicitly asks for JIRA.

# Create from thread

When the user says **create task for … for above** (or similar):

1. The bootstrap step may already have created the task from the thread — **confirm** using the bootstrap block; do not create a duplicate.
2. If bootstrap did not run, call `slack_fetch_thread` when the user references the thread (`above`, `this`, `here`) or when replying in a thread, then `slack_board_create_task` with:
   - **title** from the phrase after "for" (e.g. "payment timeout on checkout")
   - **description** from summarized thread text

# Update / assign / status

- Reference tasks by display id (`TS-123`) or say **this task** right after creating one in the same thread.
- Status labels match the board: Not picked, In progress, Review, Done.
- Direct prompts (no agent loop): `@alfred move TS-3 to in progress`, `@alfred assign TS-3 to @user`.
- Tool path: `slack_board_update_task` when routed through the planner.

# Search / list

- Use `slack_board_search_tasks` or `slack_board_get_task` for lookups.
- Reply with display id, title, status, and assignee when available.

# Comments

- Use `slack_board_comment` to post in the Slack thread linked to the task when the user asks to comment on a ticket.

# Guardrails

- Never claim a task was created/updated without a successful tool or bootstrap result.
- If board tools fail with scope errors, tell the user to add `lists:read` and `lists:write` and reinstall the Slack app.
