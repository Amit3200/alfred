# Alfred: Routing, Tools & Anti-Hallucination Architecture Plan

> **Status:** Planning document (2026-08-05)  
> **Scope:** Architecture and design only — no implementation in this doc  
> **Goal:** Make Alfred generic, reliable, and goal-driven with clear routing, complete tools, and grounded outputs

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Root Causes](#2-root-causes)
3. [Design Principles](#3-design-principles)
4. [Target Architecture Overview](#4-target-architecture-overview)
5. [Routing Redesign](#5-routing-redesign)
6. [Tool Surface & Gaps](#6-tool-surface--gaps)
7. [Prompt Fixtures & Grounding Contracts](#7-prompt-fixtures--grounding-contracts)
8. [Memory & Context Layer](#8-memory--context-layer)
9. [Script Repository Support](#9-script-repository-support)
10. [Skill / Playbook Restructure](#10-skill--playbook-restructure)
11. [Configuration Schema (Generic Deployment)](#11-configuration-schema-generic-deployment)
12. [Implementation Phases](#12-implementation-phases)
13. [Success Metrics & Acceptance Tests](#13-success-metrics--acceptance-tests)
14. [LLM-Based Tool Scoping & Discovery](#14-llm-based-tool-scoping--discovery)
15. [Multi-Subagent Orchestration](#15-multi-subagent-orchestration)
16. [LangGraph Evaluation & Adoption Path](#16-langgraph-evaluation--adoption-path)
17. [Skill System Evolution](#17-skill-system-evolution)
18. [Tools Module Structure, Classes & Logging](#18-tools-module-structure-classes--logging)
19. [Hermes Agent Runner — Audit & Reliability Plan](#19-hermes-agent-runner--audit--reliability-plan)

---

## 1. Problem Statement

Alfred has solid integration plumbing but fails in production on four recurring axes:

| Symptom | Example from Slack |
|---------|---------------------|
| **Context mixture** | Redirect metrics CSV from thread A reused when user asks for Google Sheet in thread B |
| **Tool hallucination** | "I can't create a Google Sheet" → then claims it created a Google Doc with a fabricated link |
| **Routing misfire** | JIRA move/assign requests routed to conversational summarize skill with no tools |
| **Workspace lock-in** | `TS` / `TECH` / `TECH-SUPPORT` hardcoded in `backend/routing/jira_context.py` |

The user experience breaks trust: outputs look plausible but are wrong, incomplete, or impossible given actual tool access.

---

## 2. Root Causes

### 2.1 Routing is fragmented across two uncoupled layers

```
Message
  → SkillRouter (keyword → heuristic → BM25 → LLM)     ← picks playbook
  → Context assembly (JIRA + Google + Git + Slack)     ← injects everything relevant-ish
  → detect_direct_action()                              ← only runs AFTER skill is chosen
  → ReAct loop OR direct tool OR conversational reply
```

**Failure modes:**

- A misrouted skill blocks direct tools even when intent is unambiguous (`detect_direct_action` requires the matched skill's `allowed_tools` to include the tool).
- Keyword tier ignores thread/session; later tiers use it — inconsistent behavior on short follow-ups ("yes, create the sheet").
- JIRA create is intentionally excluded from direct routing but relies on fragile skill + LLM path with a processor fallback hack.

### 2.2 Hardcoded workspace logic

Current code in `jira_context.py`:

```python
_INTENT_PROJECT_KEY_RE = re.compile(r"\b(TS|TECH)\b(?:\s+board)?", re.I)
# Special cases: "ts board", "on ts", TECH excluded when TECH-SUPPORT appears
# "#tech-support" channel name hint
```

This belongs in **config**, not Python. New deployments should never require code changes for project aliases.

### 2.3 Skill docs ≠ tool allowlists

| Skill | Markdown says use | `allowed_tools` includes |
|-------|-------------------|--------------------------|
| `jira_ticket` | `transition_jira_issue`, `add_jira_comment`, `list_jira_issues` | `get_jira_issue`, `link_jira_issue`, `jira_search` only |
| `jira_management` | Full lifecycle management | Missing `transition_jira_issue`, `link_jira_issue` |
| `google_workspace` | Read/write/create sheets | No `google_create_sheet` tool exists at all |

The model reads instructions it cannot execute → describes actions in prose → hallucination.

### 2.4 Conversational skills with no verification tools

`summarize_bugs` and similar skills have **zero tools**. They rely entirely on Slack context injected into the prompt. When context is thin, truncated, or mixed from prior turns, the model fills gaps with invented counts, dates, and ticket states.

### 2.5 Context blocks are assembled additively, not scoped

`processor.py` concatenates repo, git, JIRA, Google, and PR blocks based on integration enablement and active skill — but:

- Prior assistant turns in session may reference data not in current thread.
- Google context extracts IDs from thread; JIRA context injects project scope from channel — these can conflict.
- No explicit **"ground truth for this turn"** contract telling the model what is authoritative vs historical.

### 2.6 Duplicate / ambiguous tool schemas

- `add_jira_comment` and `jira_add_comment` — same handler, two names
- `list_jira_issues` and `jira_search` — overlapping behavior
- Google sheet `values` parameter is a JSON **string**, not a native array — models malform it frequently

---

## 3. Design Principles

### P1 — Config over code
All workspace-specific routing (project keys, board aliases, channel→project maps, assignee maps) lives in `.alfred/config.yaml` or `.alfred/routing.yaml`. Zero hardcoded project keys in Python.

### P2 — Intent before skill
Resolve **what the user wants to do** (intent class + entities) before picking a skill. Skill selection follows intent, not the reverse.

### P3 — Tool truth is singular
One canonical tool catalog. Skill `allowed_tools` must be a subset of implemented tools. Skill markdown must not reference tools outside its allowlist.

### P4 — No tool, no claim
If a capability has no tool, the model must say so explicitly and offer the nearest supported alternative. Never prose-simulate tool results.

### P5 — Scoped context per turn
Each turn gets a **ContextEnvelope**: only data fetched or verified for this intent. Session metadata provides pointers (active ticket, active sheet), not full prior responses.

### P6 — Goal-driven execution
Every routed task produces a **GoalSpec** (what done looks like) validated before and after tool runs. Summaries must cite tool result IDs, not memory.

### P7 — Generic by default
Bundled skills in `skills/` are templates. Company playbooks in `.alfred/playbooks/` override triggers and procedures. No FlexyPe-specific strings in core routing.

---

## 4. Target Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         INGRESS (Slack / CLI / UI)                  │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 1: INTENT RESOLVER (new)                                     │
│  • Entity extraction: issue keys, sheet URLs, @mentions, date ranges│
│  • Intent class: jira.read | jira.write | google.create | ...       │
│  • Confidence score + fallback to LLM classifier if ambiguous       │
│  • Output: IntentResult { class, entities, confidence }           │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 2: CONTEXT SCOPER (new)                                      │
│  • Fetch only what IntentResult requires                            │
│  • Build ContextEnvelope { slack, jira, google, repo, scripts }     │
│  • Resolve workspace aliases from config (not regex)                │
│  • Attach session pointers: active_jira_ticket, active_spreadsheet  │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 3: SKILL SELECTOR (refactored SkillRouter)                   │
│  • Map IntentResult.class → candidate skills                        │
│  • Filter by channel, repo, tool availability                       │
│  • Tiered: entity-direct → keyword → BM25 → LLM                    │
│  • Output: SkillMatch { skill, allowed_tools, mode }                │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 4: DIRECT ACTION GATE (refactored detect_direct_action)      │
│  • Runs when intent + entities are unambiguous AND tool exists      │
│  • No longer blocked by wrong skill if intent confidence ≥ threshold│
│  • Returns structured ToolResult → formatted reply                  │
└─────────────────────────────────────────────────────────────────────┘
                                    │ (if not direct)
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 5: GOAL EXECUTOR (ReAct / workflow)                          │
│  • GoalSpec injected into system prompt                             │
│  • Tool schemas = SkillMatch.allowed_tools ONLY                     │
│  • Post-tool validation: did we achieve GoalSpec?                   │
│  • Structured output formatter (not free-form prose for data)         │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 6: SESSION & MEMORY                                          │
│  • Update active entities from verified tool results                │
│  • Optional repo doc index (Graphify / RAG) for Q&A                 │
│  • Never store fabricated assistant claims as facts                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. Routing Redesign

### 5.1 Replace hardcoded JIRA logic with config-driven aliases

**New config section** (`.alfred/config.yaml` or `.alfred/routing.yaml`):

```yaml
jira:
  default_project: TECH
  allowed_projects: [TECH, TS, ENG]
  
  # Board/display name → project key (replaces TS/TECH/TECH-SUPPORT regex)
  project_aliases:
    "tech-support": TS
    "tech support": TS
    "ts board": TS
    "engineering": TECH
    TECH-SUPPORT: TS          # explicit: board name ≠ project key
  
  # Slack channel ID → default project for unqualified requests
  channel_projects:
    C0123ABC: TS              # #tech-support
    C0456DEF: TECH
  
  assignee_map:
    U01234567: alice@company.io
    "Alice Smith": alice@company.io
```

**Resolution priority** (config-driven, same for all deployments):

1. Explicit issue key in message (`PROJ-123`)
2. Explicit project key or alias in message (via `project_aliases`)
3. `channel_projects[channel_id]`
4. `list_jira_sync.jira_project` if sync enabled for channel
5. `default_project` / `allowed_projects`

**Remove from Python:** `_INTENT_PROJECT_KEY_RE`, `#tech-support` string check, TS issue-type special case → move to config:

```yaml
jira:
  project_issue_types:
    TS: Task
    default: Bug
```

### 5.2 Intent taxonomy

Define a closed set of intent classes. Each maps to skills, tools, and context requirements.

| Intent Class | Triggers (examples) | Required Context | Primary Tools | Skill |
|--------------|--------------------|--------------------|---------------|-------|
| `jira.read.single` | "status of ENG-123", JIRA URL | issue key | `get_jira_issue` | `jira_ticket` |
| `jira.read.list` | "my open tickets", "tickets assigned to @Alice" | project scope, assignee | `jira_search` | `jira_management` |
| `jira.write.create` | "create ticket for…", "log a bug" | project, assignee | `jira_create_issue` | `jira_management` |
| `jira.write.update` | "update description of…" | issue key | `jira_update_issue` | `jira_management` |
| `jira.write.transition` | "move to Done", "change status" | issue key, target status | `transition_jira_issue` | `jira_ticket` |
| `jira.write.assign` | "assign PROJ-123 to @Alice" | issue key, assignee | `jira_assign_issue` *(new)* | `jira_management` |
| `jira.write.comment` | "add comment on…" | issue key | `jira_add_comment` | `jira_management` |
| `jira.write.link` | "link PR to ticket" | issue key, URL | `link_jira_issue` | `jira_ticket` |
| `jira.write.delete` | "delete ticket" | issue key | `jira_delete_issue` *(new)* | `jira_management` |
| `google.read.sheet` | "read this sheet", sheet URL | spreadsheet_id | `google_read_sheet` | `google_workspace` |
| `google.write.sheet` | "update row 5", "append rows" | spreadsheet_id | `google_write/append_sheet` | `google_workspace` |
| `google.create.sheet` | "create a sheet from this CSV" | title, data | `google_create_sheet` *(new)* | `google_workspace` |
| `google.create.doc` | "create a doc with…" | title, body | `google_create_doc` | `google_workspace` |
| `google.rename` | "rename this doc/sheet" | file_id | `google_rename_file` *(new)* | `google_workspace` |
| `google.summarize` | "summarize this doc" | file_id | `google_read_doc/sheet` | `google_workspace` |
| `slack.summarize.thread` | "summarize this thread" | thread messages | *(read-only, no write tools)* | `summarize_thread` *(new)* |
| `slack.summarize.alerts` | "summarize bugs last week" | channel history | `fetch_slack_history` *(new read tool)* | `summarize_bugs` |
| `script.run` | "run redirect metrics", "execute X script" | script name, args | `run_company_script` | `aws_query` / custom |
| `script.list` | "what scripts are available" | — | `list_company_scripts` | schedule/aws |
| `repo.query` | "where is X defined", "how does Y work" | repo mirror | `grep_repo`, `query_graph` | `investigate_bug` |
| `repo.docs.qa` | "what does our runbook say about…" | doc index | `search_repo_docs` *(new)* | `repo_knowledge` *(new)* |
| `git.pr.review` | "review PR #123" | PR ref | `get_pr`, `get_pr_changes` | `review_pr` |
| `identity.lookup` | "what's @Alice's JIRA email" | @mention | `lookup_user_identity` | `jira_management` |
| `cross.assign_jira` | "assign this to @Alice on JIRA" | thread context → ticket | `jira_create/assign` | `jira_management` |

### 5.3 Intent resolver flow

```
Input: task.cleaned_intent + task.raw_text + thread_context + session.metadata

Step 1 — Entity extraction (deterministic regex + URL parsers)
  • JIRA keys, URLs
  • Google sheet/doc IDs
  • GitHub PR URLs
  • Slack @mentions → user IDs
  • Date ranges ("last week", "since July 22")
  • Script names (against manifest)

Step 2 — Intent classification
  • Rule-based matchers per intent class (high confidence)
  • If multiple matches or confidence < 0.7 → LLM classifier with closed label set
  • LLM classifier receives ONLY: message, entities, channel, last 2 session turns
  • Output must be one of Intent Class enum values

Step 3 — Context requirements
  • Each intent class declares required_context: [slack_thread, jira_project, ...]
  • Context scoper fetches only declared slices

Step 4 — Skill mapping
  • intent_class → default skill (configurable override in playbooks)
  • Verify skill.allowed_tools ⊇ intent.required_tools
  • If gap → fail fast with admin-visible warning, not silent hallucination
```

### 5.4 Direct action gate (decoupled from skill)

Current problem: direct action requires skill match first.

**New behavior:**

```
if intent.confidence >= 0.9
   and intent.required_tools.length == 1
   and all tools available
   and not governance-blocked:
     execute direct → return
else:
     proceed to skill + ReAct
```

Examples that should always direct-route:

- "ENG-123" or "status of ENG-123" → `get_jira_issue`
- "list my open tickets" with resolved assignee → `jira_search` with built JQL
- Sheet URL + "read this" → `google_read_sheet`

Examples that should NOT direct-route (need LLM planning):

- "create a sheet from the CSV above" (multi-step: parse attachment → create → write)
- "move this ticket to the other board" (needs project/board disambiguation)

### 5.5 Routing tier simplification

| Tier | Input | Purpose | Change |
|------|-------|---------|--------|
| **T0: Entity-direct** | Extracted entities + intent rules | Unambiguous tool calls | **New** — runs before skill router |
| **T1: Intent→skill** | Intent class | Pick skill + tool subset | **New** — replaces ad-hoc heuristics |
| **T2: Keyword** | Trigger keywords in playbooks | Company-specific overrides | Keep, but scoped to intent candidates |
| **T3: BM25** | Intent + thread snippet | Fuzzy skill match | Keep |
| **T4: LLM** | Intent + thread + catalog | Last resort | Keep, constrained to intent candidates |

**Remove / consolidate:**

- Duplicate `create_pr` checks in engine + heuristics
- FlexyPe-specific git hints ("cipher repo") → config `git.repo_aliases`
- Separate `jira_management` vs `jira_ticket` ambiguity → unified `jira` skill with intent-based tool subsets

---

## 6. Tool Surface & Gaps

### 6.1 Current inventory (45 tools)

<details>
<summary>Full current tool list by integration</summary>

**JIRA (9 + 2 identity):** `jira_search`, `list_jira_issues`, `get_jira_issue`, `jira_create_issue`, `jira_update_issue`, `transition_jira_issue`, `add_jira_comment`, `jira_add_comment`, `link_jira_issue`, `lookup_user_identity`, `build_workspace_identity_map`

**Google (6):** `google_read_sheet`, `google_write_sheet`, `google_append_sheet`, `google_read_doc`, `google_create_doc`, `google_append_doc`

**Git (16):** `list_my_prs`, `list_prs`, `get_pr`, `get_pr_changes`, `list_repos`, `grep_repo`, `read_file`, `git_log`, `git_blame`, `git_show`, `git_prepare_branch`, `write_file`, `write_debug_script`, `run_debug_script`, `git_commit`, `git_push_branch`, `create_pull_request`, `query_graph`

**AWS (3):** `athena_query`, `cloudwatch_query`, `list_cloudwatch_log_groups`

**Scripts (5):** `list_company_scripts`, `read_company_script_file`, `write_company_script_file`, `create_company_script_package`, `run_company_script`

**Schedules (5):** `create_schedule`, `list_schedules`, `toggle_schedule`, `delete_schedule`, `update_schedule`

**Web (1):** `web_search`

</details>

### 6.2 Required new tools

#### JIRA

| Tool | Purpose | API | Priority |
|------|---------|-----|----------|
| `jira_assign_issue` | Assign/reassign existing issue | `PUT /issue/{key}/assignee` | **P0** |
| `jira_update_fields` | Priority, labels, components, custom fields | `PUT /issue/{key}` | P1 |
| `jira_delete_issue` | Delete issue (governed) | `DELETE /issue/{key}` | P1 |
| `jira_list_transitions` | Read available transitions before write | `GET /issue/{key}/transitions` | P1 |
| `jira_move_to_project` | Move issue across projects/boards | `POST /issue/{key}/move` | **P0** — "move to another board" |
| `jira_link_issues` | Native issue-to-issue link | `POST /issueLink` | P2 |
| `jira_add_attachment` | Attach file from Slack export | `POST /issue/{key}/attachments` | P2 |
| `jira_get_changelog` | Audit trail for summaries | `GET /issue/{key}?expand=changelog` | P1 |

**Consolidation:**

- Deprecate `add_jira_comment` → single `jira_add_comment`
- Deprecate `list_jira_issues` → single `jira_search` with friendly params
- Merge `jira_management` + `jira_ticket` skills OR sync allowlists completely

#### Google Workspace

| Tool | Purpose | API | Priority |
|------|---------|-----|----------|
| `google_create_sheet` | Create spreadsheet with title + optional tab/data | `spreadsheets.create` | **P0** |
| `google_create_sheet_tab` | Add worksheet to existing spreadsheet | `spreadsheets.batchUpdate` | P1 |
| `google_rename_file` | Rename doc or sheet | Drive `files.update` | **P0** |
| `google_share_file` | Share with email/domain | Drive permissions | P1 |
| `google_list_drive_files` | Search Drive by name | Drive `files.list` | P1 |
| `google_update_doc` | Replace/update doc body (not just append) | Docs API | P1 |
| `google_export_file` | Export sheet as CSV/PDF for Slack attachment | Drive export | P2 |

**Schema fix (P0):** Change `values` parameter from JSON string to native `array` type in tool schema.

#### Slack (new read tools — Slack is currently ingress-only)

| Tool | Purpose | Priority |
|------|---------|----------|
| `slack_fetch_thread` | Explicit thread fetch for summarize skills | **P0** |
| `slack_fetch_channel_history` | Time-bounded history for alert summaries | **P0** |
| `slack_get_permalink` | Ground links in summaries | P2 |

These are **read-only** tools callable by summarize skills so the model verifies message text instead of inventing it.

#### Repo knowledge (memory layer)

| Tool | Purpose | Priority |
|------|---------|----------|
| `search_repo_docs` | BM25/semantic search over `.alfred/context/` + mirrored docs | **P0** |
| `read_repo_doc` | Fetch specific doc by path | P0 |
| `list_repo_docs` | Discover available runbooks/READMEs | P1 |

Leverages existing Graphify for code; adds parallel index for markdown/runbooks.

### 6.3 Tool capability matrix (target state)

| Capability | Tool(s) | Governed |
|------------|---------|----------|
| Create ticket | `jira_create_issue` | Yes |
| Fetch ticket | `get_jira_issue` | No |
| Search tickets | `jira_search` | No |
| Summarize ticket | `get_jira_issue` + `jira_get_changelog` | No |
| Move ticket (status) | `jira_list_transitions` → `transition_jira_issue` | Yes |
| Move ticket (project/board) | `jira_move_to_project` | Yes |
| Assign ticket | `jira_assign_issue` | Yes |
| Delete ticket | `jira_delete_issue` | Yes |
| Change status | `transition_jira_issue` | Yes |
| Comment | `jira_add_comment` | Yes |
| Link PR | `link_jira_issue` | Yes |
| Create sheet | `google_create_sheet` | Yes |
| Write/append sheet | `google_write_sheet`, `google_append_sheet` | Yes |
| Read sheet | `google_read_sheet` | No |
| Create doc | `google_create_doc` | Yes |
| Rename doc/sheet | `google_rename_file` | Yes |
| Summarize doc/sheet | read tools + structured formatter | No |
| Run script | `run_company_script` | Configurable |
| Sync scripts | CLI/admin (existing remote repo sync) | Admin |
| Slack thread summarize | `slack_fetch_thread` → formatter | No |
| Repo Q&A | `search_repo_docs` → `read_repo_doc` | No |
| Cross: assign on JIRA from Slack | `jira_assign_issue` + identity resolution | Yes |

---

## 7. Prompt Fixtures & Grounding Contracts

### 7.1 The problem with current prompts

Prompts mix **instructions**, **context**, and **implicit permissions**. The model cannot tell:

- Which data is from this thread vs prior session
- Which tools it actually has this turn
- What "done" looks like

### 7.2 Prompt assembly layers (target)

Each turn assembles exactly these blocks in order:

```
1. SYSTEM: Alfred identity + global rules
2. SYSTEM: Grounding contract (anti-hallucination fixture)
3. SYSTEM: Active skill body (from matched playbook)
4. SYSTEM: Tool manifest (this turn only — names + one-line descriptions)
5. SYSTEM: ContextEnvelope (scoped facts)
6. SYSTEM: GoalSpec (what success looks like)
7. USER: Slack user message with thread history
```

### 7.3 Grounding contract (fixed fixture — never paraphrased)

```markdown
## Grounding rules (mandatory)

1. **Tool boundary:** You may ONLY claim actions performed via tools listed in "Tool manifest" below.
   If a needed tool is not listed, say: "I don't have a tool for X. I can do Y instead."

2. **No fabricated artifacts:** Never invent URLs, file names, ticket keys, row counts, or dates.
   Every data point must come from a tool result or Slack context labeled [thread] below.

3. **Citation:** When stating facts from tools, prefix with source:
   - [jira:ENG-123] status is In Progress
   - [sheet:abc123] 29 rows in range A1:C30
   - [thread] user asked for CSV at 12:44 AM

4. **Summaries:** For summarize tasks, first call the appropriate read tool.
   If the tool returns empty/partial data, report the limitation — do not fill gaps.

5. **Multi-step goals:** If GoalSpec requires steps you cannot complete, stop after the last
   successful step and state what remains — do not pretend later steps succeeded.

6. **Prior assistant messages:** Treat your earlier replies as untrusted until re-verified by tool.
   Session history is for conversational continuity, not factual ground truth.
```

### 7.4 Tool manifest fixture

Instead of passing 15 tool schemas and hoping the model notices, inject an explicit manifest:

```markdown
## Tool manifest (this turn)

You have EXACTLY these tools:
- `google_create_sheet` — Create a new spreadsheet. Does NOT exist? → tell user.
- `google_write_sheet` — Write data to existing spreadsheet.
- `google_read_sheet` — Read range from existing spreadsheet.
...

You do NOT have: google_delete_sheet, jira_delete_issue, ...
```

This manifest is generated from `SkillMatch.allowed_tools` intersected with registered tools. **It is the single source of truth** — skill markdown cannot contradict it.

### 7.5 GoalSpec fixture

For each intent, generate a machine-readable goal:

```yaml
goal:
  intent: google.create.sheet
  success_criteria:
    - spreadsheet created via google_create_sheet
    - data from thread attachment or prior tool result written via google_write_sheet
    - reply includes spreadsheet URL from tool result
  failure_response: "Could not create sheet: {reason}. Attached CSV instead."
```

The executor validates: if success criteria not met, use `failure_response` template — never fake success.

### 7.6 Structured output for data-heavy replies

| Output type | Formatter | Model role |
|-------------|-----------|------------|
| JIRA ticket summary | `format_jira_issue()` | Model adds analysis only |
| Sheet/CSV export | Slack file attachment from tool data | Model writes brief intro only |
| Thread summary | Template with sections + counts from tool | Model fills brackets from data |
| Redirect metrics report | Script tool result → table renderer | No model-generated rows |

**Rule:** If the response contains tabular data, the table comes from code rendering tool output, not model markdown.

---

## 8. Memory & Context Layer

### 8.1 Current state

| Layer | What it stores | Limitation |
|-------|---------------|------------|
| Session (`session.turns`) | Last N user/assistant messages | Assistant messages may contain hallucinations |
| Session metadata | `active_jira_ticket`, `active_pr`, `last_git_action` | Pointers only — good |
| Slack context snapshot | Cached thread text | Can go stale; no relevancy re-rank on follow-up |
| Repo context (`.alfred/context/`) | Generated overview from main repo | Static; not queryable at runtime except via grep/graphify |
| Graphify | Code structure knowledge graph | Code only, not runbooks |

### 8.2 Target: three-tier memory

```
┌────────────────────────────────────────────────────────────┐
│ TIER 1: Turn Context (ephemeral)                           │
│ • ContextEnvelope built per request                        │
│ • Discarded after response                                 │
│ • Source: Slack API, JIRA API, Google API, git mirror      │
└────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────┐
│ TIER 2: Session State (thread-scoped, SQLite)              │
│ • active_jira_ticket, active_spreadsheet, active_doc       │
│ • last_verified_tool_results (IDs + hashes, not prose)     │
│ • intent_history (last 3 intent classes)                   │
│ • TTL: thread inactive 24h → prune                         │
└────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────┐
│ TIER 3: Repo Knowledge (persistent, indexed)               │
│ • Markdown docs, runbooks, READMEs from mirrored repos   │
│ • Company playbooks from .alfred/playbooks/                │
│ • Index: BM25 + optional embeddings (Graphify or separate)│
│ • Refreshed on mirror sync                                 │
│ • Queried via search_repo_docs — never injected wholesale  │
└────────────────────────────────────────────────────────────┘
```

### 8.3 Repo doc Q&A flow (anti-hallucination)

```
User: "What does our redirect runbook say about Shopify stores?"

1. Intent: repo.docs.qa
2. Tool: search_repo_docs(query="redirect Shopify", top_k=5)
3. Tool: read_repo_doc(path="docs/runbooks/redirect.md") for top hit
4. Model: answer ONLY from returned doc text, cite [doc:path#section]
5. If no hits: "No runbook found for X. Available docs: {list_repo_docs}"
```

**Never** inject the entire repo context (~8k chars) into every prompt. Query on demand.

### 8.4 Session metadata: verified facts only

After each tool run, store:

```json
{
  "active_jira_ticket": "ENG-123",
  "verified_results": {
    "ENG-123": { "tool": "get_jira_issue", "fetched_at": "...", "status": "In Progress" }
  }
}
```

When user says "update it" / "move it", resolve "it" from `active_jira_ticket` — but **re-fetch** before write operations.

---

## 9. Script Repository Support

### 9.1 Current state

- Scripts live in `.alfred/scripts/` with `script.yaml` manifests
- Remote sync via git (`docs/scripts/remote-repo.md`)
- Tools: list, read, write, create package, run
- Runtimes: python3, bash, node, deno, go

### 9.2 Target: script-aware routing

```yaml
# .alfred/scripts/redirect_metrics/script.yaml
name: redirect_metrics
description: Export redirect issue metrics from Shopify stores
triggers:
  - redirect metrics
  - redirection report
  - redirect csv
args:
  since:
    type: date
    default: "-7d"
output:
  type: csv
  filename: redirect-metrics.csv
```

**Routing:**

1. Intent resolver matches trigger phrases → `script.run` with script name
2. Direct route if all required args extracted from message
3. Otherwise skill `script_runner` with GoalSpec to collect args then run

### 9.3 Script output handling

| Output type | Delivery |
|-------------|----------|
| CSV/JSON | Slack file attachment (from tool result bytes) |
| Text | Code-block formatted reply |
| Google Sheet request | Chain: script → `google_create_sheet` → `google_write_sheet` |
| Error | Structured error with exit code + stderr snippet |

**Rule:** Script results are ground truth. Model summarizes script stdout; never regenerates the data.

### 9.4 MD file management in script repo

Scripts repo may contain runbooks (`*.md`). These are:

- Indexed in Tier 3 repo knowledge on sync
- NOT loaded into script execution context automatically
- Referenced via `search_repo_docs` when user asks procedural questions

---

## 10. Skill / Playbook Restructure

### 10.1 Proposed skill catalog (generic bundled)

| Skill | Mode | Intent classes served | Tools |
|-------|------|----------------------|-------|
| `jira` | investigation | all `jira.*` | Full JIRA tool set |
| `google_workspace` | investigation | all `google.*` | Full Google tool set |
| `summarize_thread` | investigation | `slack.summarize.thread` | `slack_fetch_thread` |
| `summarize_alerts` | investigation | `slack.summarize.alerts` | `slack_fetch_channel_history` |
| `repo_knowledge` | investigation | `repo.docs.qa`, `repo.query` | `search_repo_docs`, `read_repo_doc`, `grep_repo`, `query_graph` |
| `script_runner` | investigation | `script.run`, `script.list` | company script tools |
| `investigate_bug` | investigation | code investigation | git local + aws + web |
| `review_pr` | investigation | `git.pr.review` | PR tools + graphify |
| `create_pr` | workflow | PR creation flow | git write tools |
| `schedule_management` | investigation | cron management | schedule tools |
| `plan_task` | workflow | planning | none |
| `identity` | investigation | `identity.lookup` | identity tools |

**Key change:** Merge `jira_management` + `jira_ticket` → single `jira` skill with all JIRA tools. Intent resolver picks the subset needed; allowlist is complete.

### 10.2 Company playbooks (`.alfred/playbooks/`)

Company-specific procedures override generic skills:

```markdown
---
name: redirect_report
description: Redirect metrics report for Shopify stores
extends: script_runner
trigger_keywords:
  - redirect metrics
  - redirection issue
intent_classes:
  - script.run
script: redirect_metrics
follow_up_actions:
  - intent: google.create.sheet
    when: "create sheet|google sheet|spreadsheet"
---

# Redirect Report

1. Run `redirect_metrics` script with date from user message or default -7d
2. Attach CSV to Slack
3. If user asks for Google Sheet:
   a. `google_create_sheet` with title "Redirect Report — {date}"
   b. `google_write_sheet` with script output rows
   c. Reply with sheet URL from tool result
4. Never claim sheet was created without tool confirmation
```

### 10.3 Skill validation (CI check)

Add a linter that verifies:

- Every tool referenced in skill markdown ∈ `allowed_tools`
- Every `allowed_tools` entry ∈ `ALL_KNOWN_TOOLS`
- No hardcoded project keys in skill bodies
- Trigger keywords don't overlap ambiguously without intent class disambiguation

---

## 11. Configuration Schema (Generic Deployment)

### 11.1 Minimal config for a new company

```yaml
branding:
  company_name: Acme Corp

jira:
  enabled: true
  base_url: https://acme.atlassian.net/
  default_project: ENG
  project_aliases:
    "support board": SUP
    "eng board": ENG
  channel_projects: {}        # fill after Slack install
  assignee_map: {}

google:
  enabled: true
  # OAuth setup via admin UI

slack:
  enabled: true
  allowed_channels: ["*"]

git:
  enabled: true
  default_org: acme
  main_repo: acme/backend

routing:
  # Optional overrides
  intent_llm_fallback: true
  direct_action_confidence_threshold: 0.9
  
scripts:
  enabled: true
  remote:
    repo_url: https://github.com/acme/alfred-scripts
    branch: main
    sync_on_startup: true

repo_knowledge:
  enabled: true
  doc_paths:
    - "docs/**"
    - "runbooks/**"
    - ".alfred/playbooks/**"
  index_refresh: on_mirror_sync
```

### 11.2 What moves out of Python into config

| Currently hardcoded | Config key |
|--------------------|------------|
| `TS`, `TECH` regex | `jira.project_aliases` |
| `#tech-support` channel hint | `jira.channel_projects` |
| `TECH-SUPPORT` board name handling | `jira.project_aliases.TECH-SUPPORT` |
| TS issue type = Task | `jira.project_issue_types.TS` |
| "cipher repo" git hint | `git.repo_aliases` |
| FlexyPe loading messages | `slack.loading_messages` (already config) |
| `list_jira_sync.jira_project` default `TS` | Remove default; require explicit config |

---

## 12. Implementation Phases

### Phase 0 — Stop the bleeding (1–2 weeks)

No architecture rewrite. Quick alignment fixes:

- [ ] Sync all skill `allowed_tools` with skill markdown (especially `jira_ticket`)
- [ ] Add `google_create_sheet` tool (in `google/sheets/create.py` once folder exists, or flat file interim)
- [ ] Add `jira_assign_issue` tool
- [ ] Add grounding contract to `prompts.py`
- [ ] Add tool manifest injection per turn
- [ ] Move TS/TECH/TECH-SUPPORT from `jira_context.py` to config `project_aliases`
- [ ] Fix Google sheet `values` schema to native array
- [ ] Add `backend/tools/base/` with `BaseTool` + structured logging
- [ ] Unify `catalog.py` and `observability/tools.py` domain mapping
- [ ] Add `scripts/tools/run_tool.py` and `validate_tools.py`
- [ ] Unify `hermes_runner.py` + `loop.py` → shared `agent/runner.py`
- [ ] Add synthesis fallback to Hermes loop (parity with ReAct)
- [ ] Replace 3-line Hermes prompt with full autonomous grounding fixture
- [ ] Add grounding gate test: no URL in reply without tool trace proof

**Acceptance:** User can say "create a google sheet from this CSV" and get a real sheet URL or explicit failure.

### Phase 1 — Intent resolver + Tool Planner (2–3 weeks)

- [ ] Define `IntentClass` enum and entity extractors
- [ ] Build `ToolPlanner` LLM node (replaces `LLMSkillMatcher` as primary router)
- [ ] Build tool catalog formatter for planner prompts
- [ ] Refactor context assembly into `ContextEnvelope` builder
- [ ] Scoped tool binding from plan (not skill allowlist)
- [ ] Decouple direct action gate from skill match
- [ ] Add `jira_move_to_project`, `jira_list_transitions`
- [ ] Add Slack read tools for summarize skills

**Acceptance:** "Move ENG-123 to Done" and "assign ENG-123 to @Alice" work reliably. Tool plan logged in admin for every request.

### Phase 2 — Subagents + goal validation (2–3 weeks)

- [ ] Define capability bundles (`jira`, `google`, `slack_read`, `repo`, `script`)
- [ ] Implement worker spawner with parallel step execution
- [ ] StepResult schema + deterministic merger
- [ ] GoalSpec generation and post-execution validation
- [ ] Structured output formatters for JIRA, sheets, CSV
- [ ] Session `verified_results` metadata
- [ ] Skill linter in CI
- [ ] Deprecate phrase heuristics as primary router (keep entity-direct fast path)

**Acceptance:** "Run redirect metrics and create a Google Sheet" completes in one request with real sheet URL. No data tables in model prose.

### Phase 2b — LangGraph orchestration (2–3 weeks, can overlap Phase 2)

- [ ] Add `langgraph` optional dependency
- [ ] Define `AlfredTaskState` and graph nodes (see Section 16.4)
- [ ] Wrap existing ReAct loop as `run_worker` node
- [ ] Move governance confirmation to LangGraph `interrupt()`
- [ ] LangGraph checkpoint for pause/resume across confirmations
- [ ] Keep old `SkillRouter` as fallback behind feature flag

**Acceptance:** Write confirmation pause/resume works via graph interrupt. Graph state visible in Admin UI.

### Phase 3 — Repo knowledge + plan templates (2–3 weeks)

- [ ] Doc indexer on mirror sync
- [ ] `search_repo_docs` + `read_repo_doc` tools
- [ ] `repo_knowledge` skill
- [ ] Script trigger routing from manifests

**Acceptance:** "What does our runbook say about X" returns cited doc excerpts or explicit "not found".

### Phase 4 — Generic hardening (ongoing)

- [ ] Migrate skills → policies + capability bundles
- [ ] Plan templates in `.alfred/playbooks/` replace keyword triggers
- [ ] Remove all remaining hardcoded workspace strings from routing/
- [ ] Admin UI for routing config (project aliases, channel maps, capability toggles)
- [ ] Routing/plan debugger in Admin UI (graph trace)
- [ ] Deprecate `SkillRouter` keyword/heuristic tiers entirely
- [ ] Optional LangSmith integration for graph trace export

---

## 13. Success Metrics & Acceptance Tests

### 13.1 Routing accuracy

| Test message | Expected intent | Expected tool(s) | Must NOT |
|-------------|----------------|------------------|----------|
| "create a google sheet of the above" (after CSV) | `google.create.sheet` | `google_create_sheet`, `google_write_sheet` | Claim doc created instead |
| "move PROJ-123 to Done" | `jira.write.transition` | `transition_jira_issue` | Describe transition without tool call |
| "assign PROJ-123 to @Alice" | `jira.write.assign` | `jira_assign_issue` | Say "assigned" without tool |
| "move this to the TS board" | `jira.write.move` | `jira_move_to_project` | Confuse TECH-SUPPORT board with TECH project |
| "summarize this thread" | `slack.summarize.thread` | `slack_fetch_thread` | Invent messages not in thread |
| "run redirect metrics" | `script.run` | `run_company_script` | Generate CSV from memory |
| "what does the redirect runbook say" | `repo.docs.qa` | `search_repo_docs` | Answer from training data |

### 13.2 Anti-hallucination metrics

- **Fabricated URL rate:** 0% — every URL in response must match a tool result field
- **Tool claim accuracy:** 100% — no claimed actions without corresponding tool call in trace
- **Summary grounding:** ≥95% of stated counts verifiable against tool output or Slack message IDs
- **Context bleed:** 0% — data from thread A must not appear in thread B responses

### 13.3 Observability

Log per turn:

```json
{
  "intent_class": "google.create.sheet",
  "intent_confidence": 0.95,
  "skill": "google_workspace",
  "tools_available": ["google_create_sheet", "..."],
  "tools_called": ["google_create_sheet", "google_write_sheet"],
  "goal_achieved": true,
  "context_sources": ["slack_thread", "session.active_attachment"]
}
```

Admin UI: routing debugger showing intent → skill → tools → results chain.

---

## 14. LLM-Based Tool Scoping & Discovery

### 14.1 Problem with phrase-based routing today

Alfred currently routes through **four phrase-heavy layers**:

| Layer | Mechanism | Weakness |
|-------|-----------|----------|
| Keyword | `trigger_keywords` substring match in skill frontmatter | Misses paraphrases; false positives on shared words ("ticket", "bug") |
| Heuristics | Regex in `heuristics.py`, `jira_direct.py`, `jira_intent.py` | Workspace-specific; brittle on follow-ups ("yes, do that") |
| BM25 | Keyword overlap on skill name/description | Good fuzzy match, but still skill-level not tool-level |
| LLM skill router | Picks **one skill name** from catalog | Does not pick tools; skill may have wrong allowlist |

Direct actions (`detect_direct_action`) add a fifth phrase layer — regex for "assigned to", "list open tickets", etc.

**Result:** Routing picks a skill; tool availability is an afterthought. The model then improvises when the skill's tools don't match the actual request.

### 14.2 Target: tool-first, not skill-first

Flip the routing question:

```
OLD: "Which skill handles this message?"
NEW: "Which tools does this goal require, and in what order?"
```

Skills become **execution policies** (governance, prompts, confirmation rules), not routing destinations.

### 14.3 Three-stage LLM scoping pipeline

Replace phrase routing with a hybrid pipeline that uses LLM where language is ambiguous and code where facts are extractable.

```
┌─────────────────────────────────────────────────────────────────┐
│ STAGE A: Deterministic entity extraction (always, no LLM)       │
│ • Issue keys, URLs, @mentions, dates, attachment refs           │
│ • Session pointers: active_jira_ticket, active_spreadsheet      │
│ Output: EntityBag                                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ STAGE B: LLM Tool Planner (cheap model, structured JSON)        │
│ Input: user message + EntityBag + Tool Catalog summary          │
│ Output: ToolPlan { goal, steps[], tools_needed[], confidence }  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ STAGE C: Tool Scope Validator (code, no LLM)                    │
│ • tools_needed ⊆ registered tools                               │
│ • governance check per tool                                     │
│ • if gap → explicit "missing tool X" response, NOT hallucination│
│ • if single-step + high confidence → direct execute             │
│ • else → bind scoped tools to executor                          │
└─────────────────────────────────────────────────────────────────┘
```

### 14.4 Tool catalog for LLM discovery (not skill catalog)

Instead of sending the LLM a list of 12 skill names, send a **capability-indexed tool catalog**:

```markdown
## Tool catalog (grouped by domain)

### JIRA
- get_jira_issue(issue_key) — fetch one ticket
- jira_search(jql) — search/list tickets
- jira_create_issue(project, summary, ...) — create ticket
- jira_assign_issue(issue_key, assignee) — assign existing ticket
- transition_jira_issue(issue_key, status) — change status within project
- jira_move_to_project(issue_key, project) — move across boards/projects
...

### Google
- google_create_sheet(title, rows?) — CREATE new spreadsheet
- google_read_sheet(spreadsheet_id, range) — read existing sheet (requires ID)
- google_write_sheet(spreadsheet_id, range, values) — write to EXISTING sheet
...

### Slack (read)
- slack_fetch_thread(channel, thread_ts) — fetch thread for summarization
```

**Key difference from today:** Each tool entry states **preconditions** (create vs read, requires ID vs not). This directly prevents "I can't create a sheet" → "here's a doc I made up" failures.

### 14.5 Tool Planner prompt fixture

```markdown
You are Alfred's Tool Planner. Given the user message, entities, and tool catalog,
produce a JSON plan. Do NOT execute tools. Do NOT invent tool names.

{
  "goal": "<one sentence>",
  "confidence": 0.0-1.0,
  "steps": [
    { "tool": "<exact_tool_name>", "purpose": "<why>", "args_hint": {} }
  ],
  "missing_capabilities": ["<if any tool needed but not in catalog>"],
  "requires_subagents": false,
  "subagent_tasks": []
}

Rules:
1. Only use tools from the catalog.
2. If the goal cannot be achieved with available tools, set missing_capabilities
   and steps=[] — do NOT substitute prose for tool calls.
3. For "create sheet from CSV above", plan: google_create_sheet → google_write_sheet.
4. For "move ticket to X board", use jira_move_to_project, NOT transition_jira_issue.
5. For summarize requests, ALWAYS include a read tool (slack_fetch_thread, get_jira_issue, etc.)
   before any summary step.
6. Prefer the minimum tool set. Max 6 steps in plan.
```

**Model choice:** Use the existing `ai.routing.skill_matching` route (cheap/fast model). Tool planning replaces skill matching — same cost tier, better output.

### 14.6 When to keep deterministic shortcuts (not everything goes to LLM)

LLM scoping is not a replacement for all routing. Keep **deterministic fast paths**:

| Condition | Action | Why |
|-----------|--------|-----|
| Bare issue key in message | Direct `get_jira_issue` | Zero LLM latency |
| Sheet/doc URL + "read" | Direct read tool | URL parser is reliable |
| Governance confirmation reply ("yes, proceed") | Resume pending plan | No re-planning needed |
| Scheduled job execution | Pre-bound tool from schedule manifest | Fully deterministic |

Everything else → Tool Planner.

### 14.7 Scoped tool binding (solving the allowlist mismatch)

Today: skill has 7 tools, model sees 7 tools, skill markdown references 12.

**Target:** Tool Plan produces `tools_needed: ["google_create_sheet", "google_write_sheet"]`. Executor receives **exactly those schemas** — no more, no less. Skill markdown becomes governance prose, not the tool source of truth.

```python
# Conceptual — not implementation
scoped_tools = validate_and_bind(tool_plan.tools_needed, registry, governance)
run_agent_loop(..., allowed_tools=scoped_tools)
```

This eliminates the `jira_ticket.md` says transition but allowlist excludes it class of bugs permanently.

### 14.8 Phrase routing deprecation plan

| Current | Target | Timeline |
|---------|--------|----------|
| `trigger_keywords` in skills | Optional boost for BM25 catalog only | Phase 2 |
| `heuristics.py` regex routes | Replaced by Tool Planner | Phase 2 |
| `LLMSkillMatcher` (skill pick) | Replaced by Tool Planner | Phase 1 |
| `detect_direct_action` regex | Kept for entity-direct fast path only | Phase 1 |
| BM25 skill match | Fallback when Tool Planner confidence < 0.5 | Phase 2 |
| Keyword match | Removed from primary path | Phase 3 |

---

## 15. Multi-Subagent Orchestration

### 15.1 Why single-agent ReAct is slow and error-prone

Current flow (`backend/agent/loop.py`):

```
One LLM ↔ one tool list ↔ up to 20 iterations ↔ sequential
```

Problems for Alfred's workload:

| Request type | Single-agent pain |
|--------------|-------------------|
| "Summarize thread + create JIRA + assign @Alice" | 3 domains, 10+ tool calls, context bloat |
| "Run redirect metrics and put in a Google Sheet" | Script output → sheet write; model may garble CSV rows |
| "Review PR and link to ticket" | Git + JIRA cross-domain; one model loses focus |
| Parallel independent lookups | Sequential when they could run concurrently |

### 15.2 Target: Planner + Specialist Subagents

```
                    ┌─────────────────┐
                    │  Tool Planner   │  ← cheap LLM, produces ToolPlan
                    │  (orchestrator) │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
     ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
     │ JIRA Worker │ │Google Worker│ │ Slack Worker│
     │ tools: jira*│ │ tools: goog*│ │ tools: slack*│
     │ model: fast │ │ model: fast │ │ model: fast │
     └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
            │              │              │
            └──────────────┼──────────────┘
                           ▼
                    ┌─────────────────┐
                    │ Result Merger   │  ← deterministic + optional LLM polish
                    │ + Goal Validator│
                    └─────────────────┘
```

**Subagent = scoped tool registry + scoped system prompt + isolated context**, not a separate product or Slack bot.

### 15.3 Subagent types (specialists)

| Subagent | Tool scope | When spawned | Model tier |
|----------|-----------|--------------|------------|
| `jira_worker` | All `jira_*`, identity tools | Plan step domain = jira | `investigation` route |
| `google_worker` | All `google_*` | Plan step domain = google | `investigation` route |
| `slack_worker` | `slack_fetch_*` only | Summarize/fetch steps | `basic_chat` route |
| `script_worker` | `run_company_script`, `list_*` | Script execution steps | `investigation` route |
| `repo_worker` | `grep_repo`, `query_graph`, `search_repo_docs` | Code/doc Q&A steps | `investigation` route |
| `git_worker` | Git API + local read tools | PR review, repo queries | `pr_review` route |

Each worker:
- Receives **only its step(s)** from the ToolPlan
- Gets **domain context** only (JIRA context block for jira_worker, not Google)
- Returns **structured StepResult** (not prose)
- Cannot call tools outside its scope

### 15.4 Parallel vs sequential execution

Tool Planner marks steps with dependencies:

```json
{
  "steps": [
    { "id": "s1", "tool": "run_company_script", "args": {"script": "redirect_metrics"}, "depends_on": [] },
    { "id": "s2", "tool": "google_create_sheet", "depends_on": ["s1"] },
    { "id": "s3", "tool": "google_write_sheet", "depends_on": ["s2"], "args_from": {"rows": "s1.output.rows"} },
    { "id": "s4", "tool": "slack_fetch_thread", "depends_on": [], "parallel_group": "summarize" },
    { "id": "s5", "tool": "get_jira_issue", "depends_on": [], "parallel_group": "summarize", "args": {"issue_key": "ENG-123"} }
  ]
}
```

**Execution engine rules:**
- Steps with no mutual `depends_on` and same `parallel_group` → run concurrently
- Steps with `args_from` → receive prior step output as typed data, not LLM paraphrase
- Write steps always sequential after their read dependencies
- Governance confirmation pauses the graph, not individual workers

### 15.5 Subagent context isolation (anti-hallucination)

Each subagent prompt contains:

```markdown
## Your assignment
Execute ONLY step s2 from the plan: create a Google Sheet titled "Redirect Report".

## Input from prior step (verified)
[s1.output]: 29 rows, columns [Store name, Shopify order link, Reason]
Source: run_company_script redirect_metrics, fetched_at 2026-08-05T14:30:00Z

## Tools available
- google_create_sheet
- google_write_sheet

## Rules
- Use rows from [s1.output] verbatim — do not regenerate data
- Return StepResult JSON with spreadsheet_url from tool result
```

The orchestrator never asks the Google worker to "summarize the thread" — scope is enforced by construction.

### 15.6 Result merger

After workers complete, a **deterministic merger** assembles the Slack reply:

```python
# Priority order for reply assembly
1. GoalSpec.success_criteria check (all steps succeeded?)
2. Structured blocks from StepResults (URLs, counts, tables)
3. Optional LLM "polish" pass with ONLY StepResults as input (no tools)
4. If polish pass → validate no new facts introduced (diff check)
```

This is where "clear outputs" come from — tables and links are rendered by code from tool results, LLM only writes the intro sentence.

### 15.7 When NOT to spawn subagents

Keep single-agent ReAct for:

- Simple 1–2 tool requests ("status of ENG-123")
- Conversational chitchat
- Workflow skills with strict linear steps (`create_pr` — already a workflow mode)

**Rule:** If ToolPlan has ≤2 steps in one domain → single worker, no orchestration overhead.

---

## 16. LangGraph Evaluation & Adoption Path

Reference: [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)

### 16.1 What LangGraph provides

LangGraph is a **low-level orchestration runtime** for stateful agent workflows. Core capabilities relevant to Alfred:

| LangGraph feature | Alfred need | Fit |
|-------------------|------------|-----|
| Mix deterministic + agentic steps in one graph | Tool Planner (LLM) → direct tool (code) → subagent (LLM) | **High** |
| Stateful persistence / resume | Slack confirmation pauses, long script runs | **High** |
| Human-in-the-loop interrupts | Governance confirmation ("yes, proceed") | **High** |
| Parallel node execution | Subagent parallel_group | **Medium** |
| Checkpointing across failures | Task queue retry, resume after crash | **Medium** |
| Streaming | Slack loading messages, partial results | **Low** (nice-to-have) |

LangGraph does **not** provide: tool definitions, JIRA/Slack integrations, governance, skill markdown parsing. Alfred keeps all of those.

### 16.2 What Alfred already has that overlaps

| Alfred component | LangGraph equivalent | Keep Alfred version? |
|------------------|---------------------|---------------------|
| ReAct loop (`agent/loop.py`) | Agent node with tool calling | Replace with graph node |
| Session metadata (`models/session.py`) | Graph state / checkpoint | Merge — LangGraph state is richer |
| Task queue + worker (`orchestrator/worker.py`) | Durable execution | Keep queue; graph runs inside worker |
| Governance confirmation | `interrupt()` human-in-the-loop | **LangGraph is better here** |
| Skill router (`routing/engine.py`) | Conditional edges in graph | Replace routing with graph edges |
| Config-driven providers (`ai/routing.py`) | Model selection per node | Keep Alfred's — already clean |

### 16.3 Recommendation: adopt LangGraph for orchestration, not for everything

**Verdict: Yes, but surgically.** LangGraph fits Alfred's orchestration layer. It does not replace Alfred's integrations, tools, governance, or config system.

```
┌──────────────────────────────────────────────────────────────┐
│ Alfred (keep)                                                │
│ • Integrations: JIRA, Slack, Google, Git, AWS, scripts       │
│ • Tool registry + schemas                                    │
│ • Governance + confirmation                                  │
│ • Config + Admin UI                                          │
│ • Prompt fixtures + grounding contracts                      │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ LangGraph (adopt)                                            │
│ • Graph definition: plan → scope → execute → validate      │
│ • State: TaskState { entities, tool_plan, step_results, ... }│
│ • Nodes: extract_entities, plan_tools, run_worker, merge   │
│ • Edges: conditional on confidence, governance, step deps    │
│ • Checkpoints: SQLite via LangGraph persistence              │
│ • Interrupts: governance confirmation pause/resume           │
└──────────────────────────────────────────────────────────────┘
```

**Do NOT adopt:**
- LangChain as a required dependency for integrations (Alfred's tool registry is cleaner)
- LangChain's prebuilt agent abstractions (too opaque for governance requirements)
- LangSmith as mandatory (Alfred has observability/checkpoints; LangSmith is optional add-on)

**Optional:** `langgraph` package only (~no langchain required for basic graphs per their docs).

### 16.4 Proposed Alfred graph (LangGraph nodes)

```python
# Conceptual graph — not implementation

graph = StateGraph(AlfredTaskState)

graph.add_node("extract_entities", extract_entities_node)      # deterministic
graph.add_node("plan_tools", plan_tools_node)                    # LLM (cheap)
graph.add_node("validate_plan", validate_plan_node)              # deterministic
graph.add_node("direct_execute", direct_execute_node)            # deterministic, fast path
graph.add_node("spawn_workers", spawn_workers_node)              # parallel subagents
graph.add_node("run_worker", run_worker_node)                      # per-domain ReAct
graph.add_node("merge_results", merge_results_node)                # deterministic
graph.add_node("validate_goal", validate_goal_node)              # deterministic
graph.add_node("format_reply", format_reply_node)                  # deterministic + optional polish
graph.add_node("governance_gate", governance_gate_node)            # interrupt if write

graph.add_edge(START, "extract_entities")
graph.add_edge("extract_entities", "plan_tools")
graph.add_edge("plan_tools", "validate_plan")

graph.add_conditional_edges("validate_plan", route_after_validation, {
    "direct": "direct_execute",
    "multi_step": "spawn_workers",
    "missing_tools": "format_reply",       # fail fast with explicit message
    "needs_confirmation": "governance_gate",
})

graph.add_edge("spawn_workers", "run_worker")   # parallel map
graph.add_edge("run_worker", "merge_results")
graph.add_edge("direct_execute", "validate_goal")
graph.add_edge("merge_results", "validate_goal")
graph.add_edge("validate_goal", "format_reply")
graph.add_edge("governance_gate", "spawn_workers")  # after human approval
graph.add_edge("format_reply", END)
```

### 16.5 AlfredTaskState schema

```python
@dataclass
class AlfredTaskState:
    # Input
    task_id: str
    intent: str
    thread_context: str
    channel_id: str

    # Stage A output
    entities: EntityBag

    # Stage B output
    tool_plan: ToolPlan | None
    plan_confidence: float

    # Execution
    step_results: dict[str, StepResult]
    pending_confirmation: GovernanceRequest | None

    # Output
    reply: str
    goal_achieved: bool
    tools_called: list[str]

    # Session (persisted via LangGraph checkpoint)
    active_jira_ticket: str | None
    active_spreadsheet: str | None
    verified_results: dict[str, Any]
```

This replaces the current pattern of patching `session.metadata` ad hoc after each tool call.

### 16.6 Migration path (avoid big-bang rewrite)

| Phase | Change | Risk |
|-------|--------|------|
| **LG-0** | Add `langgraph` as optional dep; wrap existing ReAct loop as `run_worker` node | Low |
| **LG-1** | Replace `SkillRouter` primary path with `plan_tools` node; keep old router as fallback | Medium |
| **LG-2** | Move governance confirmation to LangGraph `interrupt()` | Medium |
| **LG-3** | Add parallel `spawn_workers` for multi-domain plans | Medium |
| **LG-4** | Deprecate phrase heuristics; graph is sole orchestrator | Low (after LG-1 stable) |
| **LG-5** | LangGraph checkpoint replaces session metadata for active entities | Medium |

**Principle:** Each phase ships independently. Slack users see improvement after LG-1 (tool scoping), not after full LangGraph migration.

### 16.7 LangGraph vs custom orchestrator — decision matrix

| Criterion | Custom (extend current) | LangGraph |
|-----------|------------------------|-----------|
| Time to multi-subagent | 4–6 weeks custom scheduler | 2–3 weeks with graph primitives |
| Governance pause/resume | Manual session flags (current) | Native interrupts |
| Observability | Custom checkpoints (existing) | Graph state visualization |
| Dependency weight | Zero | +1 package (`langgraph`) |
| Team familiarity | Already in codebase | New pattern to learn |
| Control over execution | Full | Full (low-level by design) |
| Vendor coupling | None | Low (can eject — graph is declarative) |

**Decision:** LangGraph for orchestration graph + checkpoints + interrupts. Alfred owns everything else.

### 16.8 What LangGraph does NOT solve

- Tool hallucination → still need Tool Plan validator + grounding contracts (Section 7)
- Missing tools → still need to implement `google_create_sheet`, etc. (Section 6)
- Workspace-specific config → still need `project_aliases` (Section 5)
- Skill markdown drift → still need linter (Section 10.3)

LangGraph is the **execution skeleton**, not the **brain**.

---

## 17. Skill System Evolution

### 17.1 Current skill model and its limits

Skills today are **monolithic routing units**:

```yaml
# skills/jira_management.md
trigger_keywords: [jira, ticket, bug, ...]   # 20+ overlapping triggers
allowed_tools: [jira_search, jira_create_issue, ...]  # static list
mode: investigation
```

Problems:
1. Triggers overlap across 12 skills → keyword tier misfires
2. `allowed_tools` is both routing gate and execution scope → two jobs, one field
3. Skill body is long procedural markdown the model may ignore or contradict
4. Conversational skills (`summarize_bugs`) have no tools → guaranteed hallucination risk
5. Company-specific logic leaks into bundled skills (`TS` issue type in jira_management.md)

### 17.2 Target: skills as governance policies, not routing targets

Split skill definition into three independent artifacts:

```
┌────────────────────┐
│ Capability Bundle  │  ← what tools exist in a domain (jira, google, slack_read)
│ (code/registry)    │
└─────────┬──────────┘
          │
┌─────────▼──────────┐
│ Tool Plan (LLM)    │  ← which tools this request needs (dynamic, per turn)
└─────────┬──────────┘
          │
┌─────────▼──────────┐
│ Execution Policy   │  ← governance, confirmation, output format (was "skill")
│ (markdown/config)  │
└────────────────────┘
```

**Routing no longer picks a skill.** Tool Planner picks tools; policy layer applies rules.

### 17.3 New skill frontmatter schema

```yaml
---
name: jira_policy
type: policy                    # policy | workflow | deprecated_skill
domain: jira
capability_bundle: jira         # maps to registry bundle
governance:
  write_tools_require_confirmation: true
  allowed_channels: ["*"]
  allowed_projects_from_config: true
output:
  format: jira_summary          # structured formatter
  cite_tool_results: true
prompt:
  role: "JIRA operations assistant"
  rules:
    - "Use jira_move_to_project for cross-board moves"
    - "Never use currentUser() when assignee resolved from @mention"
trigger_keywords: []            # deprecated — empty for new policies
---
```

Workflow skills (`create_pr`) keep `type: workflow` with a **fixed step graph** — these are the exception where routing is deterministic.

### 17.4 Capability bundles (replace static allowed_tools)

Defined in code/config, not markdown:

```yaml
# .alfred/capabilities.yaml (new)
bundles:
  jira:
    tools: [get_jira_issue, jira_search, jira_create_issue, jira_assign_issue,
             transition_jira_issue, jira_move_to_project, jira_add_comment, ...]
    context_injectors: [jira_context]
    subagent: jira_worker

  google:
    tools: [google_create_sheet, google_read_sheet, google_write_sheet,
             google_create_doc, google_read_doc, google_rename_file, ...]
    context_injectors: [google_context]
    subagent: google_worker

  slack_read:
    tools: [slack_fetch_thread, slack_fetch_channel_history]
    context_injectors: [slack_context]
    subagent: slack_worker
```

Tool Planner selects from union of enabled bundles. Subagent spawner uses bundle→worker mapping.

### 17.5 Playbook evolution for company-specific work

Company playbooks (`.alfred/playbooks/`) become **plan templates**, not routing triggers:

```yaml
---
name: redirect_report
type: plan_template
triggers:
  - redirect metrics
  - redirection report
plan_template:
  steps:
    - tool: run_company_script
      args: { script: redirect_metrics }
    - tool: google_create_sheet
      title: "Redirect Report — {date}"
    - tool: google_write_sheet
      args_from: { rows: "step_0.output" }
follow_up:
  - when: "google sheet|spreadsheet"
    insert_after: step_0
    steps: [google_create_sheet, google_write_sheet]
---
```

When Tool Planner confidence < 0.7, check plan templates for trigger match → use template instead of LLM plan. This replaces keyword routing with **structured plan reuse**.

### 17.6 Conversational skills → read-tool-backed policies

| Old skill | Problem | New approach |
|-----------|---------|--------------|
| `summarize_bugs` | No tools, prose from thin context | Policy + mandatory `slack_fetch_channel_history` step in plan |
| `summarize_bugs` response format | Model ignores 4-section template | Deterministic formatter on fetched messages; LLM only classifies brackets |
| `summarize_thread` (new) | — | `slack_fetch_thread` → structured summary formatter |

**Key insight:** Summarization becomes a **two-node graph**: fetch (tool) → classify/format (LLM with strict input boundary).

### 17.7 Skill linter rules (extended)

| Rule | Check |
|------|-------|
| No `trigger_keywords` on new policies | Enforce empty or deprecated |
| No tool names in markdown body outside `plan_template` | Body is governance only |
| Every `plan_template` step references valid tool | CI check against registry |
| No hardcoded project keys in any markdown | Regex scan for `\b[A-Z]{2,10}-\d+\b` patterns in prose ok, project key lists not ok |
| `capability_bundle` must exist in capabilities.yaml | Schema validation |

---

## 18. Tools Module Structure, Classes & Logging

### 18.1 Current problems

The tools layer grew organically and has structural debt:

| Problem | Where | Impact |
|---------|-------|--------|
| Flat file layout | `backend/tools/jira_tool.py`, `google_tool.py`, `git_api.py` all siblings | Hard to navigate; `git_api.py` registers *every* integration |
| Google Sheets + Docs mixed | `google_tool.py` (261 lines, 6 tools) | Sheet and doc logic not separable; harder to add `google_create_sheet` cleanly |
| No Slack LLM tools | Slack is ingress-only in `integrations/slack/` | Summarize/fetch must become tools with no home |
| Handlers as nested closures | `register_google_tools()` defines 6 inner functions | Untestable without full registry; credentials captured in closure |
| Duplicate tool catalogs | `tools/catalog.py` vs `observability/tools.py` | Google/Slack/schedule/identity tools missing from observability categories |
| Minimal logging | `registry.py` logs `Tool X completed kind=Y` only | No domain, duration, args (redacted), or structured trace |
| No base tool class | Procedural `ToolSchema` + handler functions | No shared validation, logging, error wrapping, or result typing |
| Identity tools in JIRA file | `lookup_user_identity` in `jira_tool.py` | Wrong domain boundary |

### 18.2 Target folder structure

```
backend/tools/
├── __init__.py                    # public exports: ToolRegistry, build_registry
├── registry.py                    # ToolRegistry (unchanged interface)
├── result.py                      # ToolResult + domain result types
├── catalog.py                     # ALL_KNOWN_TOOLS — single source of truth
├── selection.py                   # allowlist normalization
├── builder.py                     # build_registry() — replaces git_api.py name
│
├── base/                          # shared tool infrastructure
│   ├── __init__.py
│   ├── tool.py                    # BaseTool, ToolContext, ToolExecutionLog
│   ├── schema.py                  # schema builders, param validators
│   ├── logging.py                 # structured tool logger
│   └── errors.py                  # ToolValidationError, ToolExecutionError
│
├── jira/                          # JIRA domain
│   ├── __init__.py                # register_jira_tools(registry, ctx)
│   ├── bundle.py                  # JIRA_TOOLS frozenset + capability bundle def
│   ├── schemas.py                 # all JIRA ToolSchema constants
│   ├── read.py                    # GetIssueTool, SearchTool, ListTransitionsTool
│   ├── write.py                   # CreateIssueTool, UpdateIssueTool, AssignTool
│   ├── workflow.py                # TransitionTool, MoveProjectTool, DeleteTool
│   └── link.py                    # LinkIssueTool, AddCommentTool
│
├── git/                           # Git/GitHub domain
│   ├── __init__.py
│   ├── bundle.py
│   ├── schemas.py
│   ├── api.py                     # list_prs, get_pr, list_repos (remote API)
│   ├── local.py                   # grep, read_file, git_log, blame, show
│   └── write.py                   # branch, commit, push, create_pr
│
├── slack/                         # Slack read tools (NEW)
│   ├── __init__.py
│   ├── bundle.py
│   ├── schemas.py
│   ├── fetch_thread.py            # SlackFetchThreadTool
│   └── fetch_history.py           # SlackFetchChannelHistoryTool
│
├── google/                        # Google Workspace — split by product
│   ├── __init__.py                # register_google_tools → delegates to sheets + docs
│   ├── bundle.py                  # GOOGLE_SHEET_TOOLS, GOOGLE_DOC_TOOLS, GOOGLE_TOOLS
│   ├── drive.py                   # shared: rename, share, list (future)
│   ├── sheets/
│   │   ├── __init__.py            # register_sheet_tools()
│   │   ├── schemas.py
│   │   ├── read.py                # GoogleReadSheetTool
│   │   ├── write.py               # GoogleWriteSheetTool, GoogleAppendSheetTool
│   │   └── create.py              # GoogleCreateSheetTool (NEW)
│   └── docs/
│       ├── __init__.py            # register_doc_tools()
│       ├── schemas.py
│       ├── read.py                # GoogleReadDocTool
│       ├── create.py              # GoogleCreateDocTool
│       └── write.py               # GoogleAppendDocTool, GoogleUpdateDocTool
│
├── identity/                      # cross-domain identity (split from jira/)
│   ├── __init__.py
│   ├── bundle.py
│   ├── schemas.py
│   └── lookup.py                  # LookupUserIdentityTool, BuildWorkspaceMapTool
│
├── aws/                           # AWS domain (move from aws_tool.py)
│   ├── __init__.py
│   ├── bundle.py
│   └── ...
│
├── scripts/                       # company script tools (move from company_script_tool.py)
│   ├── __init__.py
│   ├── bundle.py
│   └── ...
│
└── web/                           # web search (move from web_search_tool.py)
    ├── __init__.py
    └── ...

backend/integrations/              # UNCHANGED role: API clients, no ToolSchema
├── jira/api.py                    # JiraApiClient — HTTP only
├── google/sheets.py               # read_sheet, write_sheet, create_sheet
├── google/docs.py                 # read_doc, create_doc, append_doc
├── slack/context.py               # fetch helpers used BY slack tools
└── git/api.py                     # GitApiClient
```

**Rule:** `backend/tools/` = LLM-facing schemas + handlers. `backend/integrations/` = raw API clients. Tools call integrations; integrations never import tools.

### 18.3 Class hierarchy

Every tool is a class implementing a common contract:

```python
# backend/tools/base/tool.py

@dataclass(frozen=True)
class ToolContext:
    """Immutable context passed to every tool execution."""
    config: AlfredConfig
    data_dir: Path
    task_id: str | None
    session_key: str | None
    source: str                    # slack | cli | ui | scheduler
    channel_id: str | None
    user_id: str | None


class BaseTool(ABC):
    """Base class for all Alfred tools."""

    name: ClassVar[str]
    domain: ClassVar[str]          # jira | git | slack | google_sheet | google_doc | ...
    operation: ClassVar[str]       # read | write | create | delete | search
    requires_confirmation: ClassVar[bool] = False

    @classmethod
    @abstractmethod
    def schema(cls) -> ToolSchema: ...

    @classmethod
    def category(cls) -> str:
        """Observability category — defaults to domain."""
        return cls.domain

    def validate_args(self, args: dict[str, Any]) -> dict[str, Any]:
        """Normalize and validate arguments. Raise ToolValidationError."""
        ...

    @abstractmethod
    def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        """Run the tool. Integration calls happen here."""
        ...

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        """Wrapper: validate → log start → execute → log end → return."""
        log = ToolExecutionLog.start(self.name, self.domain, args, ctx)
        try:
            validated = self.validate_args(args)
            result = self.execute(validated, ctx)
            log.finish(success=result.kind != "error", result_kind=result.kind)
            return result
        except ToolValidationError as exc:
            log.finish(success=False, error=str(exc))
            return ToolResult.error(str(exc))
        except Exception as exc:
            log.finish(success=False, error=str(exc))
            logger.exception("Tool %s failed", self.name)
            return ToolResult.error(f"Error running {self.name}: {exc}")
```

**Example — JIRA read tool:**

```python
# backend/tools/jira/read.py

class GetIssueTool(BaseTool):
    name = "get_jira_issue"
    domain = "jira"
    operation = "read"

    @classmethod
    def schema(cls) -> ToolSchema:
        return ToolSchema(
            name=cls.name,
            description="Get full details for a JIRA issue by key (e.g. ENG-123).",
            parameters={
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string", "description": "Issue key, e.g. ENG-123."},
                },
                "required": ["issue_key"],
            },
        )

    def validate_args(self, args: dict[str, Any]) -> dict[str, Any]:
        key = str(args.get("issue_key") or "").strip().upper()
        if not key or not ISSUE_KEY_RE.match(key):
            raise ToolValidationError("issue_key is required (e.g. ENG-123)")
        return {"issue_key": key}

    def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        client = JiraApiClient.from_config(ctx.config.jira)
        detail = client.get_issue(args["issue_key"])
        return ToolResult.jira_detail(detail)
```

**Example — Google Sheet create (new):**

```python
# backend/tools/google/sheets/create.py

class GoogleCreateSheetTool(BaseTool):
    name = "google_create_sheet"
    domain = "google_sheet"
    operation = "create"
    requires_confirmation = True

    @classmethod
    def schema(cls) -> ToolSchema:
        return ToolSchema(
            name=cls.name,
            description=(
                "Create a NEW Google Spreadsheet. Returns spreadsheet_id and URL. "
                "Use google_write_sheet to populate after creation."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Spreadsheet title."},
                    "sheet_name": {"type": "string", "description": "First tab name (default Sheet1)."},
                    "headers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional header row.",
                    },
                    "rows": {
                        "type": "array",
                        "items": {"type": "array"},
                        "description": "Optional initial data rows.",
                    },
                },
                "required": ["title"],
            },
        )

    def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        creds = GoogleCredentials.from_config(ctx.config.google)
        data = google_sheets.create_spreadsheet(
            title=args["title"],
            sheet_name=args.get("sheet_name", "Sheet1"),
            headers=args.get("headers"),
            rows=args.get("rows"),
            credentials=creds,
        )
        return ToolResult(kind="google_sheet", data={"action": "create", **data})
```

### 18.4 Domain bifurcation — tool inventory by folder

#### JIRA (`backend/tools/jira/`)

| File | Tool class | Tool name | Op | Status |
|------|-----------|-----------|-----|--------|
| `read.py` | `SearchTool` | `jira_search` | read | exists |
| `read.py` | `GetIssueTool` | `get_jira_issue` | read | exists |
| `read.py` | `ListTransitionsTool` | `jira_list_transitions` | read | **new** |
| `write.py` | `CreateIssueTool` | `jira_create_issue` | write | exists |
| `write.py` | `UpdateIssueTool` | `jira_update_issue` | write | exists |
| `write.py` | `AssignIssueTool` | `jira_assign_issue` | write | **new** |
| `workflow.py` | `TransitionTool` | `transition_jira_issue` | write | exists |
| `workflow.py` | `MoveProjectTool` | `jira_move_to_project` | write | **new** |
| `workflow.py` | `DeleteIssueTool` | `jira_delete_issue` | write | **new** |
| `link.py` | `AddCommentTool` | `jira_add_comment` | write | exists (drop `add_jira_comment` alias) |
| `link.py` | `LinkRemoteTool` | `link_jira_issue` | write | exists |

**Remove:** `list_jira_issues` (duplicate of `jira_search` with filters).

#### Git (`backend/tools/git/`)

| File | Tool class | Tool name | Op |
|------|-----------|-----------|-----|
| `api.py` | `ListMyPrsTool` | `list_my_prs` | read |
| `api.py` | `ListPrsTool` | `list_prs` | read |
| `api.py` | `GetPrTool` | `get_pr` | read |
| `api.py` | `GetPrChangesTool` | `get_pr_changes` | read |
| `api.py` | `ListReposTool` | `list_repos` | read |
| `local.py` | `GrepRepoTool` | `grep_repo` | read |
| `local.py` | `ReadFileTool` | `read_file` | read |
| `local.py` | `GitLogTool` | `git_log` | read |
| `local.py` | `GitBlameTool` | `git_blame` | read |
| `local.py` | `GitShowTool` | `git_show` | read |
| `write.py` | `PrepareBranchTool` | `git_prepare_branch` | write |
| `write.py` | `WriteFileTool` | `write_file` | write |
| `write.py` | `GitCommitTool` | `git_commit` | write |
| `write.py` | `GitPushBranchTool` | `git_push_branch` | write |
| `write.py` | `CreatePullRequestTool` | `create_pull_request` | write |

#### Slack (`backend/tools/slack/`) — NEW

| File | Tool class | Tool name | Op |
|------|-----------|-----------|-----|
| `fetch_thread.py` | `FetchThreadTool` | `slack_fetch_thread` | read |
| `fetch_history.py` | `FetchChannelHistoryTool` | `slack_fetch_channel_history` | read |

These wrap `backend/integrations/slack/context.py` fetch helpers. Return structured message lists for summarize formatters — never raw prose.

#### Google Sheets (`backend/tools/google/sheets/`)

| File | Tool class | Tool name | Op |
|------|-----------|-----------|-----|
| `create.py` | `GoogleCreateSheetTool` | `google_create_sheet` | create |
| `read.py` | `GoogleReadSheetTool` | `google_read_sheet` | read |
| `write.py` | `GoogleWriteSheetTool` | `google_write_sheet` | write |
| `write.py` | `GoogleAppendSheetTool` | `google_append_sheet` | write |

#### Google Docs (`backend/tools/google/docs/`)

| File | Tool class | Tool name | Op |
|------|-----------|-----------|-----|
| `create.py` | `GoogleCreateDocTool` | `google_create_doc` | create |
| `read.py` | `GoogleReadDocTool` | `google_read_doc` | read |
| `write.py` | `GoogleAppendDocTool` | `google_append_doc` | write |
| `write.py` | `GoogleUpdateDocTool` | `google_update_doc` | write (future) |

#### Google Drive (`backend/tools/google/drive/`) — future shared

| Tool class | Tool name | Op |
|-----------|-----------|-----|
| `GoogleRenameFileTool` | `google_rename_file` | write |
| `GoogleShareFileTool` | `google_share_file` | write |
| `GoogleListFilesTool` | `google_list_drive_files` | read |

### 18.5 Registration pattern

Replace nested closures with explicit tool class registration:

```python
# backend/tools/builder.py (replaces git_api.py)

from backend.tools.jira import ALL_JIRA_TOOLS
from backend.tools.git import ALL_GIT_TOOLS
from backend.tools.slack import ALL_SLACK_TOOLS
from backend.tools.google.sheets import ALL_SHEET_TOOLS
from backend.tools.google.docs import ALL_DOC_TOOLS
from backend.tools.identity import ALL_IDENTITY_TOOLS

DOMAIN_REGISTRARS = [
    ("jira",      ALL_JIRA_TOOLS,      lambda cfg: cfg.jira.enabled),
    ("git",       ALL_GIT_TOOLS,       lambda cfg: cfg.git.enabled),
    ("slack",     ALL_SLACK_TOOLS,     lambda cfg: cfg.slack.enabled),
    ("google_sheet", ALL_SHEET_TOOLS, lambda cfg: cfg.google.enabled and _google_ready(cfg)),
    ("google_doc",   ALL_DOC_TOOLS,   lambda cfg: cfg.google.enabled and _google_ready(cfg)),
    ("identity",  ALL_IDENTITY_TOOLS,  lambda cfg: cfg.jira.enabled or cfg.slack.enabled),
    # aws, scripts, web, schedule ...
]

def build_registry(config: AlfredConfig, *, allowed_tools: list[str] | None = None) -> ToolRegistry:
    registry = ToolRegistry()
    registry.set_registration_filter(allowed_tools)
    ctx = ToolContext.from_config(config)

    for domain, tool_classes, enabled_fn in DOMAIN_REGISTRARS:
        if not enabled_fn(config):
            continue
        for tool_cls in tool_classes:
            tool = tool_cls()
            registry.register(
                tool_cls.schema(),
                lambda args, t=tool, c=ctx: t.run(args, c),  # or bind via functools.partial
            )
    return registry
```

Each domain's `__init__.py` exports `ALL_*_TOOLS: list[type[BaseTool]]`.

### 18.6 Logging specification

#### 18.6.1 Structured tool execution log

```python
# backend/tools/base/logging.py

@dataclass
class ToolExecutionLog:
    tool_name: str
    domain: str
    operation: str
    task_id: str | None
    session_key: str | None
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    success: bool | None = None
    result_kind: str | None = None
    error: str | None = None
    args_redacted: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def start(cls, name, domain, args, ctx) -> ToolExecutionLog: ...

    def finish(self, *, success, result_kind=None, error=None) -> None:
        self.finished_at = datetime.now(timezone.utc)
        self.duration_ms = int((self.finished_at - self.started_at).total_seconds() * 1000)
        self.success = success
        self.result_kind = result_kind
        self.error = error
        emit_tool_log(self)
        record_observability(self)
```

#### 18.6.2 Log levels and fields

| Event | Level | Fields |
|-------|-------|--------|
| Tool start | `INFO` | `tool`, `domain`, `operation`, `task_id`, `args_redacted` |
| Tool success | `INFO` | `tool`, `domain`, `duration_ms`, `result_kind`, `task_id` |
| Tool validation fail | `WARNING` | `tool`, `domain`, `error`, `args_redacted` |
| Tool execution fail | `ERROR` | `tool`, `domain`, `duration_ms`, `error` (+ stack trace) |
| Tool not in allowlist | `WARNING` | `tool`, `task_id`, `allowed_tools` |
| Governance blocked | `INFO` | `tool`, `domain`, `reason` |

**Args redaction rules:**

| Field pattern | Redaction |
|---------------|-----------|
| `api_token`, `credentials`, `password` | `[REDACTED]` |
| `comment`, `body_text`, `text`, `description` | truncate to 200 chars |
| `values`, `rows` | log row count only: `{"rows": 29, "cols": 3}` |
| `jql` | log as-is (no secrets) |
| `issue_key`, `spreadsheet_id`, `document_id` | log as-is |

#### 18.6.3 Logger naming convention

```python
# One logger per domain — filterable in log aggregation
logger = logging.getLogger("alfred.tools.jira")
logger = logging.getLogger("alfred.tools.google.sheet")
logger = logging.getLogger("alfred.tools.slack")
logger = logging.getLogger("alfred.tools.git")
```

Configure in logging setup:

```yaml
# optional .alfred/logging.yaml
loggers:
  alfred.tools:
    level: INFO
  alfred.tools.jira:
    level: DEBUG    # enable for JIRA debugging
  alfred.tools.google.sheet:
    level: INFO
```

#### 18.6.4 Observability store — fix category mapping

Replace duplicated `observability/tools.py` with import from `tools/catalog.py`:

```python
# backend/tools/catalog.py — extended

TOOL_DOMAINS: dict[str, str] = {
    "get_jira_issue": "jira",
    "jira_search": "jira",
    "google_read_sheet": "google_sheet",
    "google_create_sheet": "google_sheet",
    "google_read_doc": "google_doc",
    "google_create_doc": "google_doc",
    "slack_fetch_thread": "slack",
    "list_prs": "git",
    ...
}

def tool_domain(tool_name: str) -> str:
    return TOOL_DOMAINS.get(tool_name, "other")

def tool_category(tool_name: str) -> str:
    """Observability grouping — coarser than domain."""
    domain = tool_domain(tool_name)
    if domain.startswith("google_"):
        return "google"
    return domain
```

**Extend `record_tool_call`** to include:

```python
event = InteractionEvent(
    ...
    tool_name=tool_name,
    tool_category=tool_category(tool_name),
    tool_domain=tool_domain(tool_name),       # NEW
    tool_operation=tool_operation(tool_name),  # NEW: read|write|create
    duration_ms=duration_ms,                   # FIX: currently often None
    success=success,
    result_kind=result_kind,                   # NEW
    metadata={"args_redacted": ...},            # NEW
)
```

#### 18.6.5 Task checkpoint integration

Each tool call writes a checkpoint row (existing `observability/task_progress.py`):

```
checkpoint: jira/get_jira_issue
status: completed
detail: ENG-123 → In Progress
duration_ms: 342
```

Use `{domain}/{tool_name}` as checkpoint key for Admin UI timeline.

### 18.7 CLI scripts for tool development & ops

Add scripts under `scripts/tools/` for local testing without Slack:

```
scripts/tools/
├── README.md                      # usage guide
├── list_tools.py                  # list all registered tools by domain
├── describe_tool.py               # show schema + class for one tool
├── run_tool.py                    # execute a tool from CLI with JSON args
├── validate_tools.py              # CI: schema lint, domain coverage, no duplicates
└── smoke_test.py                  # run read-only smoke tests per integration
```

#### `scripts/tools/run_tool.py`

```bash
# Examples:
uv run python scripts/tools/run_tool.py \
  --tool get_jira_issue \
  --args '{"issue_key": "ENG-123"}'

uv run python scripts/tools/run_tool.py \
  --tool google_create_sheet \
  --args '{"title": "Test Sheet", "headers": ["A","B"], "rows": [["1","2"]]}'

uv run python scripts/tools/run_tool.py \
  --tool slack_fetch_thread \
  --args '{"channel_id": "C0123", "thread_ts": "1234.5678"}'
```

Uses `.alfred/config.yaml` for credentials. Outputs `ToolResult.to_json()` to stdout. Logs to stderr via structured logger.

#### `scripts/tools/validate_tools.py`

CI check (run in pre-commit or GitHub Actions):

```
✓ All tool classes have unique names
✓ All tools in catalog.py have a class
✓ No duplicate schemas (drop add_jira_comment alias)
✓ tool_domain() covers 100% of registered tools
✓ Google sheet tools use array type for rows (not JSON string)
✓ Write tools marked requires_confirmation=True
✓ Each domain bundle matches capability.yaml
```

#### `scripts/tools/smoke_test.py`

```bash
# Read-only integration health checks
uv run python scripts/tools/smoke_test.py --domain jira
uv run python scripts/tools/smoke_test.py --domain google_sheet
uv run python scripts/tools/smoke_test.py --domain slack
uv run python scripts/tools/smoke_test.py --all
```

Runs one safe read tool per domain (`jira_search` with `max_results=1`, etc.). Used in setup wizard "test connections" flow.

### 18.8 ToolResult typing by domain

Extend `result.py` with domain-specific constructors — keep `kind` as discriminator:

```python
# JIRA
ToolResult.jira_detail(issue: dict)
ToolResult.jira_list(issues: list[JiraIssueSummary])
ToolResult.jira_action(action: str, data: dict)   # create, transition, assign, move

# Google Sheets
ToolResult.google_sheet(action: Literal["create","read","write","append"], data: dict)
# data always includes: spreadsheet_id, url (when applicable), row_count

# Google Docs
ToolResult.google_doc(action: Literal["create","read","append","update"], data: dict)
# data always includes: document_id, url (when applicable)

# Slack
ToolResult.slack_messages(messages: list[SlackMessageDict], *, source: str)
# source: "thread" | "channel_history"

# Git
ToolResult.pr_list(...), ToolResult.pr_detail(...)  # existing
```

**Rule:** Every create tool result MUST include a `url` field when the API provides one. Formatters and GoalSpec validators check for this — prevents hallucinated links.

### 18.9 Migration from current layout

| Step | Action | Risk |
|------|--------|------|
| T-1 | Add `backend/tools/base/` with `BaseTool`, logging | None — additive |
| T-2 | Create domain folders; move schemas to `schemas.py` per domain | Low |
| T-3 | Convert one tool per domain to class (pilot) | Low |
| T-4 | Split `google_tool.py` → `google/sheets/` + `google/docs/` | Medium |
| T-5 | Add `slack/` tools | Medium |
| T-6 | Rename `git_api.py` → `builder.py`; extract git tools to `git/` | Medium |
| T-7 | Convert remaining handlers to classes | Medium |
| T-8 | Unify `catalog.py` + `observability/tools.py` | Low |
| T-9 | Add `scripts/tools/` CLI | None — additive |
| T-10 | Delete old flat files after import paths updated | Low |

Each step is independently shippable. Old import paths (`from backend.tools.jira_tool import register_jira_tools`) get thin re-export shims until T-10.

### 18.10 Testing structure (mirrors tools/)

```
tests/tools/
├── test_registry.py
├── test_catalog.py
├── jira/
│   ├── test_read.py
│   ├── test_write.py
│   └── test_workflow.py
├── google/
│   ├── sheets/test_create.py
│   └── docs/test_read.py
├── slack/
│   └── test_fetch_thread.py
└── test_logging.py               # verify redaction, duration, domain fields
```

Each tool class gets unit tests with mocked integration client — no live API calls in CI.

---

## 19. Hermes Agent Runner — Audit & Reliability Plan

Reference: [NousResearch/hermes-agent](https://github.com/nousresearch/hermes-agent) (official product — 225k+ stars, full agent platform)

### 19.1 Critical clarification: Alfred "Hermes" ≠ Nous Hermes Agent

Alfred has a config flag `orchestrator.agent_runner: "hermes"`, but this is **not** an integration of the [NousResearch/hermes-agent](https://github.com/nousresearch/hermes-agent) repository. It is a **local loop variant** in `backend/orchestrator/hermes_runner.py` — ~200 lines that duplicate `backend/agent/loop.py` with three extra system prompt lines.

| | Alfred `hermes_runner` | Official [hermes-agent](https://github.com/nousresearch/hermes-agent) |
|--|------------------------|------------------------------------------------------------------------|
| **What it is** | ReAct loop + `HERMES_SYSTEM_INSTRUCTIONS` | Full agent platform (gateway, TUI, toolsets, memory, subagents) |
| **Subagents** | None | Native parallel delegation |
| **Tool scoping** | Static skill `allowed_tools` | Dynamic toolset system (`toolsets.py`) |
| **Memory** | Session turns only | FTS5 session search, Honcho user modeling, skill creation loop |
| **Anti-hallucination** | Same as ReAct — no extra guards | Command approval, tool verification, context compression |
| **Dependencies** | None (internal code) | Standalone install (`hermes` CLI, uv, Node, etc.) |
| **Slack integration** | Alfred's processor | Hermes gateway (separate process) |

**Implication:** Setting `agent_runner: "hermes"` in Alfred does not give you Nous Hermes capabilities. It only changes the system prompt and checkpoint labels. Routing, tool allowlists, and hallucination risks are identical to ReAct.

### 19.2 Current implementation audit

#### Files involved

| File | Role |
|------|------|
| `backend/orchestrator/hermes_runner.py` | Hermes loop entry point |
| `backend/agent/loop.py` | ReAct loop; `_execute_tool` shared by Hermes |
| `backend/orchestrator/prompts.yaml` | `hermes_system_instructions` (3 bullet lines) |
| `backend/orchestrator/processor.py` | Switches on `agent_runner` |
| `tests/test_hermes_and_learning.py` | One basic tool-call test |

#### What Hermes loop actually does

```python
# hermes_runner.py — simplified flow
1. Prepend HERMES_SYSTEM_INSTRUCTIONS to system message
2. For up to 20 iterations:
   a. Inject task plan checklist (same as ReAct)
   b. provider.chat(conversation, tools=tool_schemas)
   c. If tool_calls → execute via _execute_tool (from loop.py) → append results
   d. If text tool call in prose → parse and execute (same as ReAct)
   e. If final text → return
3. Return generic failure message (no synthesis pass)
```

#### Differences vs ReAct (`loop.py`)

| Feature | ReAct | Hermes | Impact |
|---------|-------|--------|--------|
| System prompt | Base Alfred prompt | + `HERMES_SYSTEM_INSTRUCTIONS` | Minimal behavior change |
| Max iteration fallback | `_synthesize_final_answer()` — one tool-free LLM pass from gathered results | Generic "could not form final answer" | **Hermes worse** on long investigations |
| Checkpoint logging | Per-tool checkpoints | + `hermes_loop_iteration` checkpoints | Better observability in Hermes |
| Code duplication | ~240 lines | ~215 lines, 95% identical | Maintenance drift risk |
| Grounding contract | None | None | Both hallucinate equally |
| Tool manifest | None | None | Both rely on skill allowlist |
| Goal validation | None | None | Both can claim success without tool proof |

#### Current Hermes system instructions (entire fixture)

```yaml
# prompts.yaml — this is ALL that distinguishes Hermes from ReAct
hermes_system_instructions: |
  ## Hermes Agent System Directives
  - You operate in persistent autonomous mode.
  - Actively evaluate the output of each tool to determine the next optimal action.
  - Ensure that your troubleshooting traces are clean, concise, and target the root cause directly.
```

**Problem:** These directives encourage autonomous action but provide **no anti-hallucination rules**, **no tool boundary contract**, and **no "verify before claiming" requirements**. They may actually increase hallucination by telling the model to act persistently without grounding constraints.

### 19.3 Why Hermes mode still hallucinates

Hermes inherits every routing and tool problem from Sections 1–2, plus:

1. **Same broken allowlists** — Hermes uses `skill.allowed_tools` from phrase-routed skills. No improvement over ReAct.

2. **No tool-result verification before final answer** — Model can return prose after a failed tool or without calling the needed tool at all.

3. **Text-emitted tool calls** — Both loops parse tool calls from prose (`parse_text_tool_call`). Weak models emit malformed or fake tool JSON; Hermes executes if parse succeeds but model may also skip tools entirely.

4. **Plan checklist drift** — Planning prompt generates steps; model may mark steps done in prose without executing tools. `update_plan_progress` trusts model-reported actions.

5. **Missing synthesis pass** — ReAct has `_synthesize_final_answer` when iterations exhaust; Hermes does not. But neither validates that the synthesis cites only tool results.

6. **No "tool called?" gate** — For write operations (create sheet, assign ticket), nothing checks that the required tool actually ran before sending Slack reply.

7. **Misleading naming** — Operators expect Nous Hermes behavior (subagents, toolsets, memory). They get ReAct with a different label.

### 19.4 What official Hermes Agent does that Alfred should adopt (concepts, not dependency)

From [hermes-agent docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/tools) and architecture:

| Official Hermes feature | Alfred equivalent (planned) | Adopt? |
|-------------------------|----------------------------|--------|
| **Toolsets** — grouped, configurable tool bundles | Capability bundles (Section 17.4) | **Yes** — same concept |
| **Tool Planner scoping** — dynamic tool selection | Tool Planner (Section 14) | **Yes** |
| **Subagent delegation** | Domain workers (Section 15) | **Yes** |
| **Command approval** | Governance confirmation (existing) | **Yes** — already have, extend |
| **Session search / memory** | Repo doc index + verified_results (Section 8) | **Yes** — partial |
| **Trajectory compression** | Not needed for Slack bot | No |
| **Skills self-improvement loop** | `learning.py` meta-playbook generation | **Partial** — needs review gate (have) |
| **MCP servers** | Future v3 (build-reference) | Later |
| **Standalone gateway/TUI** | Alfred Admin UI + Slack listener | No — Alfred IS the product |
| **Full hermes-agent as dependency** | Would duplicate Slack, JIRA, config, governance | **No** |

**Recommendation:** Do **not** embed [hermes-agent](https://github.com/nousresearch/hermes-agent) as a Python dependency or subprocess. Alfred already has integrations, governance, and Slack ingress. Adopt Hermes **patterns** (toolsets, subagents, memory, approval) into Alfred's own orchestration graph (Section 16).

Rename internally to avoid confusion: `agent_runner: "hermes"` → `"autonomous"` or keep `"hermes"` but document clearly.

### 19.5 Target: reliable autonomous runner

Merge ReAct and Hermes into one **`AgentRunner`** with modes, shared infrastructure, and reliability gates.

```
backend/agent/
├── __init__.py
├── runner.py              # unified entry: run_agent(...)
├── react_strategy.py      # single-step tool loop (current loop.py logic)
├── autonomous_strategy.py # persistent mode (current hermes_runner logic, enhanced)
├── synthesis.py           # _synthesize_final_answer + grounded polish pass
├── grounding.py           # validate final answer against tool trace
├── execute.py             # _execute_tool (shared)
└── types.py               # AgentRunResult, ToolTrace
```

#### 19.5.1 Unified runner interface

```python
@dataclass
class AgentRunResult:
    text: str
    tool_trace: list[ToolTraceEntry]   # every tool call this run
    goal_achieved: bool
    grounding_passed: bool
    iterations_used: int

def run_agent(
    *,
    mode: Literal["react", "autonomous"],
    provider, messages, registry, allowed_tools,
    goal_spec: GoalSpec | None = None,   # from Tool Planner
    grounding_contract: str,             # fixed fixture
    tool_manifest: list[str],              # explicit this-turn tools
    ...
) -> AgentRunResult:
```

Both `react` and `autonomous` modes share:
- `_execute_tool` from `execute.py`
- Grounding contract in system prompt
- Tool manifest injection
- Tool trace recording
- Goal validation before return

**Mode difference:**

| | `react` | `autonomous` (was hermes) |
|--|---------|---------------------------|
| Iteration style | Tool → result → next tool until done | Same, but encourages multi-step chains |
| System addendum | Standard Alfred | + autonomous directives + plan-driven |
| Max iterations | 20 | 20 (configurable) |
| Synthesis fallback | Yes | Yes (fix Hermes gap) |
| Subagent spawn | No (single worker) | Yes, when ToolPlan.requires_subagents |

### 19.6 Enhanced autonomous system fixture (replace current 3 lines)

Replace `hermes_system_instructions` in `prompts.yaml` with a full grounding-aware fixture:

```yaml
autonomous_system_instructions: |
  ## Autonomous execution mode

  You operate in multi-step autonomous mode. Follow these rules strictly:

  ### Tool discipline
  1. You may ONLY claim actions that appear in the tool trace for this turn.
  2. Before stating a fact about JIRA, Google, Git, or Slack data, you MUST have
     a corresponding tool result in this conversation. If not, call the tool first.
  3. If a tool is not in the Tool manifest below, say "I don't have a tool for X"
     — never simulate the action in prose.

  ### Execution discipline
  4. After each tool result, evaluate whether the Goal (if provided) is satisfied.
     If yes, stop and respond. Do not call unnecessary tools.
  5. If a tool returns an error, report the error honestly — do not claim success.
  6. For create/write operations, the response MUST include the URL or ID from
     the tool result. Never invent links.

  ### Planning discipline
  7. Follow the Task Plan Checklist when present. Mark steps done only after
     the corresponding tool succeeds.
  8. Prefer the minimum tool sequence. Do not over-investigate.

  ### Output discipline
  9. Lead with the outcome in one sentence, then details.
  10. Cite sources: [jira:KEY], [sheet:ID], [tool:name].
  11. Tables and counts must match tool output exactly — do not round or estimate.
```

This integrates Section 7 grounding contract into the autonomous runner specifically.

### 19.7 Grounding gate before Slack reply

Add a post-loop validation step (deterministic, not LLM):

```python
def validate_agent_result(result: AgentRunResult, goal: GoalSpec | None) -> ValidationResult:
    issues = []

    # Gate 1: Write goals require tool proof
    if goal and goal.requires_write:
        write_tools_called = [t for t in result.tool_trace if t.name in goal.required_tools]
        if not write_tools_called:
            issues.append("Write goal but no write tool called")

    # Gate 2: URL claims must match tool results
    urls_in_text = extract_urls(result.text)
    urls_from_tools = extract_urls_from_trace(result.tool_trace)
    fabricated = urls_in_text - urls_from_tools
    if fabricated:
        issues.append(f"Fabricated URLs: {fabricated}")

    # Gate 3: "I created" / "I assigned" language requires matching tool
    claim_verbs = detect_action_claims(result.text)  # regex: created, assigned, moved, updated
    for claim in claim_verbs:
        if not tool_trace_supports(claim, result.tool_trace):
            issues.append(f"Claim '{claim.action}' not supported by tool trace")

    if issues:
        return ValidationResult(passed=False, issues=issues,
                                fallback=build_honest_failure_reply(result, issues))
    return ValidationResult(passed=True)
```

If validation fails, Alfred sends the fallback (honest failure + partial tool results) instead of the model's hallucinated prose.

### 19.8 Tool trace logging for Hermes/autonomous mode

Extend observability to record full trace per run:

```json
{
  "task_id": "abc-123",
  "runner": "autonomous",
  "iterations": 4,
  "tool_trace": [
    {"step": 1, "tool": "run_company_script", "success": true, "duration_ms": 3200, "result_kind": "script_output"},
    {"step": 2, "tool": "google_create_sheet", "success": false, "error": "Tool not registered"},
    {"step": 3, "tool": "google_create_doc", "success": true, "result_kind": "google_doc"}
  ],
  "grounding_passed": false,
  "grounding_issues": ["Write goal but google_create_sheet not called", "Fabricated URLs: ..."],
  "goal_achieved": false
}
```

Visible in Admin UI task timeline — operators can see exactly where autonomous mode went wrong.

### 19.9 Decision: integrate official hermes-agent or not?

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| **A. Embed hermes-agent as subprocess** | Full feature set immediately | Duplicate Slack/JIRA/config; two products to maintain; governance bypass risk | **Reject** |
| **B. Port hermes patterns into Alfred** | Single product; keeps governance; uses Alfred integrations | Engineering effort | **Recommended** |
| **C. Keep current hermes_runner as-is** | Zero work | Misleading name; no reliability improvement; duplicates ReAct | **Reject** |
| **D. Unify ReAct + Hermes + add gates (Phase 0–2)** | Fixes immediate gaps; one code path | Moderate refactor | **Do first** |

### 19.10 Implementation checklist (Hermes reliability)

#### Phase 0 — immediate (no architecture rewrite)

- [ ] Add `_synthesize_final_answer` to `hermes_runner.py` (parity with ReAct)
- [ ] Replace 3-line `hermes_system_instructions` with full autonomous fixture (19.6)
- [ ] Inject grounding contract + tool manifest into both runners
- [ ] Deduplicate: extract shared loop body from `loop.py` and `hermes_runner.py` into `agent/runner.py`
- [ ] Rename in docs/UI: "Hermes" → "Autonomous mode" with tooltip explaining it is not Nous Hermes Agent
- [ ] Add test: autonomous mode must not return URL not present in tool trace

#### Phase 1 — with Tool Planner

- [ ] Pass `GoalSpec` from Tool Planner into agent runner
- [ ] Post-loop grounding gate (19.7) before Slack reply
- [ ] Full `tool_trace` in observability store

#### Phase 2 — with LangGraph

- [ ] Autonomous mode = graph path with subagent spawn nodes
- [ ] Governance interrupt between write steps
- [ ] Deprecate separate `hermes_runner.py` — single graph executor

### 19.11 Acceptance tests (autonomous mode)

| Scenario | Must happen | Must NOT happen |
|----------|-------------|-----------------|
| "Create google sheet from CSV" (no create tool) | Reply: "I don't have google_create_sheet" | Fake doc/sheet URL |
| "Assign ENG-123 to @Alice" (no assign tool) | Reply: "I can't assign — tool missing" | "I've assigned it" |
| Script returns 29 rows → "make a sheet" | Tool trace includes create + write OR honest failure | Model-generated 29 rows in prose |
| Tool fails mid-chain | Report which step failed + partial results | Claim full success |
| 20 iterations exhausted | Synthesis pass from tool results only | Generic error with no summary |
| Write tool ran | Response includes URL/ID from `ToolResult.data` | URL not in tool output |

---

## Appendix A: Current vs Target — JIRA Flow

### Current (broken for "move to another board")

```
"move this ticket to TS board"
  → SkillRouter: jira_management (keyword: ticket)
  → allowed_tools: no transition_jira_issue, no move
  → LLM: prose description of what it would do
  → User sees: "I've moved it" (hallucination)
```

### Target

```
"move this ticket to TS board"
  → Intent: jira.write.move, entity: active_jira_ticket=ENG-123, target=TS (via alias)
  → Context: resolve TS → project key from project_aliases
  → Tools: jira_move_to_project(ENG-123, project=TS)
  → GoalSpec validated: response includes new project from tool result
  → User sees: "[jira:ENG-123] moved to project TS — https://..."
```

---

## Appendix B: Current vs Target — Google Sheet from CSV

### Current (from Slack screenshot)

```
"can you create the google sheet of above?"
  → SkillRouter: google_workspace
  → No google_create_sheet tool
  → LLM: "I can't create a sheet" then hallucinates Google Doc link
  → User gets: broken markdown table + fake doc link
```

### Target

```
"can you create the google sheet of above?"
  → Intent: google.create.sheet
  → Context: CSV data from thread attachment / prior verified result
  → Tools: google_create_sheet → google_write_sheet
  → GoalSpec: sheet URL in response from tool
  → User gets: real sheet link + optional Slack CSV attachment as backup
  → If create fails: explicit error + CSV attachment (failure_response template)
```

---

## Appendix C: File Map (implementation reference)

| Component | Current path | Target path |
|-----------|-------------|-------------|
| Skill router | `backend/routing/engine.py` | Deprecated → LangGraph conditional edges |
| Tool planner | — | `backend/routing/tool_planner.py` *(new)* |
| JIRA context | `backend/routing/jira_context.py` | Split: alias resolver (config) + prompt formatter |
| Direct actions | `backend/routing/intent.py` | Entity-direct fast path only |
| Entity extractor | — | `backend/routing/entity_extractor.py` *(new)* |
| Context scoper | — | `backend/routing/context_scope.py` *(new)* |
| Orchestration graph | — | `backend/orchestrator/graph.py` *(new, LangGraph)* |
| Subagent workers | — | `backend/agent/workers/` *(new)* |
| Goal executor | `backend/agent/loop.py` | Becomes `run_worker` graph node |
| Prompt assembly | `backend/orchestrator/prompts.py` | Add fixtures + tool catalog formatter |
| Tool registry | `backend/tools/git_api.py` | Add new tools |
| Capability bundles | — | `.alfred/capabilities.yaml` *(new)* |
| Session | `backend/models/session.py` | Merge with LangGraph checkpoint state |
| Repo index | — | `backend/context/doc_index.py` *(new)* |
| Skills | `skills/*.md` | Migrate to policies + plan templates |
| Config | `backend/models/config.py` | Add routing + alias schemas |

---

## Appendix D: Related Docs

- [`../build-reference/v0.md`](../build-reference/v0.md) — layer architecture baseline
- [`../build-reference/building_phase_v0.md`](../build-reference/building_phase_v0.md) — implementation tracker
- [`../playbooks/README.md`](../playbooks/README.md) — playbook format
- [`../scripts/remote-repo.md`](../scripts/remote-repo.md) — script sync setup
- [`../../skills/jira_management.md`](../../skills/jira_management.md) — current JIRA skill (to be migrated to policy)
- [`../../skills/google_workspace.md`](../../skills/google_workspace.md) — current Google skill
- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview) — orchestration runtime evaluation reference

## Appendix E: Architecture Decision Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Primary routing | LLM Tool Planner | Replaces phrase/skill routing; picks tools not skills |
| Phrase routing | Deprecated (entity-direct fast path only) | Brittle, workspace-specific, causes misfires |
| Skill role | Governance policy + output format | Not a routing destination |
| Multi-domain requests | Subagents with scoped tools + parallel steps | Faster, less context bleed, fewer hallucinations |
| Orchestration runtime | LangGraph (surgical adoption) | Native interrupts, graph state, parallel nodes; Alfred keeps integrations |
| LangChain dependency | Not required | Alfred's tool registry and providers are sufficient |
| Summarize skills | Fetch tool → format (two-node graph) | Cannot summarize without read tool verification |
| Tool allowlist source | Tool Plan output validated against registry | Eliminates skill markdown vs allowlist drift |
| Config vs code | All workspace aliases in config | Generic Alfred for any deployment |
| Tools folder structure | Domain packages: `jira/`, `git/`, `slack/`, `google/sheets/`, `google/docs/` | Clean bifurcation; integrations stay API-only |
| Tool implementation | `BaseTool` class per tool | Testable, consistent logging, validation |
| Tool logging | Structured `ToolExecutionLog` + domain loggers | Duration, redacted args, result_kind in observability |
| Ops scripts | `scripts/tools/run_tool.py`, `validate_tools.py`, `smoke_test.py` | CLI testing without Slack; CI schema lint |
| Hermes runner | Unify with ReAct → `AgentRunner` + grounding gate | Current "Hermes" is ReAct + 3 prompt lines, not Nous Hermes Agent |
| Official hermes-agent | Adopt patterns only (toolsets, subagents, memory) | Do not embed as dependency — Alfred keeps its own integrations |

---

*This document should be treated as the source of truth for routing/tool work until implementation completes. Update it as decisions are made.*
