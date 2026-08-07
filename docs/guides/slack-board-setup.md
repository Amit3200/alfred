# Slack List board setup & workflow

Manage Kanban tasks on **Slack Lists** from `@alfred` — create tasks from threads, update status, search the board, and optionally disambiguate vs JIRA.

Configuration is stored in **Alfred’s SQLite database** (`.alfred/alfred.db`). You do **not** need to edit `config.yaml` for each new channel, and changes apply **without restarting** Alfred.

---

## What Alfred can do

| Action | Example |
|--------|---------|
| **Setup board (recommended)** | `@alfred setup board` |
| Create task from thread | `@alfred create task for payment timeout for above` |
| Create + assign | `@alfred create task for checkout bug and assign @user` |
| Update status | `@alfred move TS-3 to in progress` |
| Assign | `@alfred assign TS-3 to @user` |
| Assign last task | `@alfred assign this task to @user` (after create in same thread) |
| Search / list | `@alfred list open tasks` |
| Get one task | `@alfred get TS-3` |
| Link existing List | `@alfred link board to F01234567` |
| Show config | `@alfred show board config` |

When both **Slack Lists** and **JIRA** are available in a channel, Alfred can show **Slack List** / **JIRA** buttons before creating a generic ticket (unless the channel policy says otherwise).

---

## Prerequisites

### 1. Slack app scopes

Reinstall the Slack app after adding scopes:

| Scope | Purpose |
|-------|---------|
| `app_mentions:read` | @alfred mentions |
| `channels:history`, `groups:history` | Thread / channel context |
| `chat:write` | Replies and comments |
| `lists:read` | Read List schema and items |
| `lists:write` | Create Lists, create/update items, set List access (`slackLists.access.set`) |
| `files:read` (recommended) | Load List schema via `files.info` |
| `users:read` (optional) | Assignee resolution |

**Interactivity** must be enabled on the Slack app (for JIRA vs List choice buttons).

### 2. Alfred Integrations

In **Settings → Integrations → Slack**:

- Slack **enabled**
- Bot token (`xoxb-…`), app token (`xapp-…`), signing secret configured (via Secrets UI)

### 3. Alfred routing (check `config.yaml`)

These should be **on** for the full LangGraph + planner path:

```yaml
routing:
  tool_planner_enabled: true
  langgraph_enabled: true
  plan_first_routing: true
```

`repo_knowledge.enabled: true` is unrelated but fine to leave on.

### 4. Deploy UI + backend

After pulling the Slack board feature:

```bash
cd frontend && npm run build
# Restart alfred serve from repo root
# Hard refresh browser (Cmd+Shift+R)
```

Admin UI: **Settings → Automation → Slack boards**

---

## One-time: create the List in Slack

**Recommended:** in the channel, run **`@alfred setup board`**. Alfred calls [`slackLists.create`](https://docs.slack.dev/reference/methods/slacklists.create), grants this channel edit access, verifies task create works, and saves the binding — no manual `F…` id.

Optional name: `@alfred setup board named Bugs tracker`.

**Manual alternative:**

1. Create or open your support channel (e.g. `#tech-support`).
2. Add a **Slack List** to the channel (e.g. “Bugs tracker”).
3. Note the **List id** (`F…`) from the List URL or share link.
4. Run `@alfred link board to F…`
5. Note the **channel id** (`C…`) from channel details (or use the UI label after binding).

Typical columns (match names in the UI binding form):

| Column | Example label |
|--------|----------------|
| Title | Name / Issue Title |
| Status | Not picked, In progress, Review, Done |
| Details | Ticket Details |
| Severity | High / Medium / Low |
| Assignee | Assignee |
| Merchant | Merchant Name |

Optional: add a column for Alfred display ids (`TS-123`) and set **Display id column** in the binding.

---

## Setup option A — Admin UI (recommended)

Open **Settings → Automation → Slack boards**.

### Tab: Board bindings

**Add board binding** for each channel that uses a List:

| Field | Example |
|-------|---------|
| Slack channel id | `C01234567` |
| Channel name | `#tech-support` (optional, for your reference) |
| Board key | `bugs-tracker` |
| List id | `F01234567` |
| Display id prefix | `TS` |
| Next number | `1` (for a new board) |
| Default status | `Not picked` |
| Column names | Match your List (Name, Status, Ticket Details, …) |
| Auto-approve writes | Off = user must confirm writes in Slack |

### Tab: Channel workflows

**Add channel workflow** for routing policy:

| Ticket system | Behavior |
|---------------|----------|
| `ask` | Show **Slack List** / **JIRA** buttons when both are enabled and the request is ambiguous |
| `slack_list` | Always use Slack List (no JIRA buttons) |
| `jira` | Always use JIRA for generic creates |

Optional **JIRA project key** (e.g. `TS`) — used for JIRA creates/search in that channel (stored in DB, not `config.yaml`).

Changes save to `.alfred/alfred.db` immediately.

---

## Setup option B — In Slack

In the target channel:

```text
@alfred setup board
@alfred setup board named "Bugs tracker"
@alfred link board to F01234567
@alfred link board to F01234567 for bugs-tracker
@alfred set ticket system ask
@alfred set display prefix TS
@alfred show board config
@alfred unlink board
```

---

## Day-to-day usage

All three core flows run **immediately from your prompt** (no LLM confirmation loop):

| Flow | Prompt |
|------|--------|
| **Add task** | `@alfred create task for payment timeout on checkout` |
| **From thread** | `@alfred create task for checkout API 500 for above` |
| **Update status** | `@alfred move TS-3 to in progress` · `@alfred set TS-3 to review` |
| **Assign** | `@alfred assign TS-3 to @user` · `@alfred assign this task to @user` |

Status labels: **Not picked**, **In progress**, **Review**, **Done**.

### Create a task from a thread

1. Discuss the issue in a **thread**.
2. In that thread:

```text
@alfred create task for checkout API 500 for above
```

Alfred will:

1. Fetch the thread text
2. Use **checkout API 500** as the title
3. Put thread content in **Ticket Details**
4. Create a List item and reply with display id / record id

Other phrasing works: `create task for merchant sync failure`, `add ticket for … for above`.

### Update / search

```text
@alfred move TS-42 to in progress
@alfred list open tasks
@alfred assign TS-42 to @user
```

Use display ids (`TS-N`) or List record ids when known.

### JIRA vs Slack List

If the channel policy is **`ask`** and JIRA is enabled:

- Generic `@alfred create ticket for …` → Alfred posts **Slack List** and **JIRA** buttons.
- Explicit phrases skip buttons:
  - `create jira ticket …` → JIRA
  - `create task on bugs tracker …` → Slack List

Reply `slack` or `jira` in the thread if you see the choice prompt without clicking.

Toggle globally in config (optional):

```yaml
slack:
  ticket_create_disambiguation: true   # default
```

---

## New channel checklist

Use this when adding another channel (e.g. `#merchant-bugs`):

| Step | Action |
|------|--------|
| 1 | Create channel + attach Slack List |
| 2 | Copy `C…` and `F…` ids |
| 3 | **Slack boards** UI → Add board binding |
| 4 | **Slack boards** UI → Add channel workflow (`slack_list` or `ask`) |
| 5 | `/invite @alfred` |
| 6 | Test: thread + `@alfred create task for … for above` |

No `config.yaml` edit or Alfred restart required for steps 3–4.

---

## Governance & writes

Board write tools (`slack_board_create_task`, `slack_board_update_task`, `slack_board_comment`) require **confirmation** in Slack when governance is enabled, unless:

- **Auto-approve writes** is on for that board binding in the UI, or
- The user approved writes in the session (`yes` / `proceed`).

Audit entries are logged when governance audit is enabled.

---

## Troubleshooting

| Symptom | Check |
|---------|--------|
| “No Slack board configured for this channel” | Run **`@alfred setup board`** or add a **board binding** for that `C…` id |
| List visible but create fails | Run **`@alfred setup board`** for a fresh Alfred-owned List, or Share existing List with @alfred (Can edit) |
| List API errors / scope errors | Reinstall Slack app with `lists:read` + `lists:write` |
| Buttons don’t respond | Slack app **Interactivity** enabled; Socket Mode running |
| Wrong column values | Column names in binding must match List column **labels** exactly |
| Always goes to JIRA, not List | Channel workflow → set `slack_list`, or bind board for that channel |
| UI missing “Slack boards” | `npm run build` in `frontend/`, restart Alfred, hard refresh |
| Display ids not incrementing | Edit **Next number** in board binding UI |

Logs: `.alfred/run/alfred.stdout.log` and **Settings → Operations → Routing** for intent/skill traces.

---

## REST API (admin)

For automation outside the UI:

| Method | Path |
|--------|------|
| GET | `/api/slack/workflows/channels` |
| PUT | `/api/slack/workflows/channels/{channel_id}` |
| DELETE | `/api/slack/workflows/channels/{channel_id}` |
| GET | `/api/slack/workflows/boards` |
| POST | `/api/slack/workflows/boards` |
| PUT | `/api/slack/workflows/boards/{id}` |
| DELETE | `/api/slack/workflows/boards/{id}` |

Requires admin auth (`X-Alfred-Token` or Basic auth).

---

## Optional: yaml fallback (legacy)

DB bindings are preferred. You can still enable yaml boards as fallback:

```yaml
slack:
  board_workflows:
    enabled: true
    boards:
      - name: bugs-tracker
        list_id: "F01234567"
        channel_ids:
          - "C01234567"
        display_id_prefix: TS
        default_status: Not picked
        columns:
          title: Name
          status: Status
          details: Ticket Details
```

Yaml changes may require a **Slack listener restart** when saving via Integrations; DB changes do not.

---

## Related

- Skill: `skills/slack_board_management.md`
- Routing intent: `slack.board.create`, `slack.board.update`, `slack.board.search`
- Implementation: commit `bd498b3` on branch `amit3200/pr/alfred/refactor-v2`
