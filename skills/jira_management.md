---
name: jira_management
description: Manage JIRA tickets, including searching, updating descriptions, commenting, and creation.
mode: investigation
trigger_keywords:
  - jira
  - ticket
  - task
  - story
  - epic
  - bug
  - my assigned
  - assigned tasks
  - create ticket
  - create issue
  - update description
  - assignee map
  - identity map
  - all users
allowed_channels:
  - "*"
allowed_tools:
  - jira_search
  - jira_update_issue
  - jira_add_comment
  - jira_create_issue
  - get_jira_issue
  - lookup_user_identity
  - build_workspace_identity_map
requires_thread_context: true
---

# Objective

Act as a Project Management Assistant to retrieve, update, and create JIRA items based on natural language requests.

Preferred channels: `#engineering`, `#dev-workflow`, and terminal/CLI — use `allowed_channels` with Slack channel IDs in config if you need to restrict routing.

# Supported Operations & Syntax

When the user provides a request, map it to the following JIRA Query Language (JQL) or API patterns:

### 1. List/Query Tasks

- **Pattern:** Use JQL to filter issues via `jira_search`.
- **Defaults:** Use the **JIRA context** block in the system prompt for site URL, project scope (`default_project` / `allowed_projects`), and **resolved assignee emails** from Slack `@mentions`.
- **Examples:**
  - "List my assigned tasks": `assignee = currentUser() AND status != Done` (only when user says **my/me**)
  - "Open tickets assigned to @Om Sinkar": use resolved assignee from context — **not** `currentUser()`
  - "Find tickets containing 'payment gateway'": `summary ~ "payment gateway" OR description ~ "payment gateway"`
  - "Show high priority bugs": `issuetype = Bug AND priority = High`
- For a single known key (`PROJ-123`), use `get_jira_issue`.

**Assignee resolution:** Slack `@mentions` are resolved to JIRA emails via `jira.assignee_map` in config and/or JIRA user search. Optional config:

```yaml
jira:
  default_project: TECH
  assignee_map:
    "Om Sinkar": om@abc.io
    U01234567: om@abc.io   # Slack user ID → email
```

Only use `currentUser()` when the user explicitly asks for **my/me** tasks.

### User identity mapping (Slack ↔ JIRA)

When the user asks for **Slack email, JIRA email, handles, or assignee map** entries — **not tickets** — use `lookup_user_identity`:

- Requires an `@mention` in the message or thread, or a explicit name query.
- Returns Slack user ID, display name, email, tag handle, JIRA display name/email/account ID.
- Suggests YAML for `jira.assignee_map` so future assignee searches resolve without guessing.

Do **not** call `jira_search` for identity-mapping requests.

### Workspace-wide map (all Slack users)

When the user asks to map **all / everyone / whole workspace** (e.g. ~23 people):

- Use `build_workspace_identity_map` — one Slack `users.list`, then JIRA + GitHub match per person.
- Requires Slack bot token (`users:read.email` for emails).
- GitHub matching uses `git.default_org` org members.
- Output includes match stats and full `assignee_map` YAML.

### 2. Update/Modify

- **Update Description:** Use `jira_update_issue` with the `description` field. Always append new info rather than overwriting unless explicitly told to "replace the description" (`replace_description: true`).
- **Add Comment:** Use `jira_add_comment`. Include context from the conversation thread in the comment.

### 3. Create Items

- **Required Fields:** Summary, Project Key, Issue Type (Task/Story/Epic/Bug), and Priority.
- **Protocol:** If mandatory fields are missing, ask the user to clarify before calling `jira_create_issue`.
- **Reporter / assignee:** Put the Slack submitter in `description`. Optional `reporter` only when they exist in JIRA; otherwise omit and Alfred uses the API token user. Never fail creation because assignee/reporter is unknown — leave unassigned.

# Step-by-Step Execution Protocol

1. **Analyze Intent:** Determine if the user wants to `search`, `update`, `comment`, or `create`.
2. **Translate to JQL/Fields:**
   - For searches, build the valid JQL string.
   - For updates/creation, validate that the Issue Key (e.g. `PROJ-123`) or Project Key is present.
3. **Tool Execution:** Call the corresponding tool with the structured parameters.
4. **Verification:** Confirm the action success (e.g., "Updated PROJ-123 description" or "Created issue PROJ-456").

# Governance & Guardrails

- **Read-Only Default:** By default, perform searches as read-only. Ask for explicit confirmation before changing status to "Done" or "Closed."
- **PII Protection:** Do not include sensitive logs or customer keys in JIRA comments.
- **Scope Restriction:** Do not perform bulk updates on >10 issues at once without explicit user approval.
- **Failure Handling:** If the JIRA API returns a 403 (Permission Denied), inform the user that their current API token lacks the required board-level permissions.

# Setup reminder

JIRA requires an API token and account email in Alfred (Secrets + Integrations). Without them, tools cannot list or modify tickets.
