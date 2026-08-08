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

When the user wants a **new task**:

1. Review the tool manifest — you have READ tools (search/get/fetch thread) and WRITE tools (create/update/comment).
2. If thread context is needed, use `slack_fetch_thread` (or the injected thread block).
3. Call **`slack_board_create_task`** with title and description — do not claim success without this write tool (or a verified bootstrap result).

# Agentic tool selection (create / update / comment)

For any mutation request:

1. **Reason** — decide create vs update vs comment vs read-only lookup.
2. **Read first when needed** — `slack_board_search_tasks`, `slack_board_get_task`, or `slack_fetch_thread` when the task id or context is unclear.
3. **Write** — call exactly one of:
   - `slack_board_create_task` — new item
   - `slack_board_update_task` — status, assignee, severity
   - `slack_board_comment` — comment on linked thread
4. Never simulate tool results in prose.

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
