# Alfred — v0 Build Status & Gaps

> **Purpose:** Living tracker of implementation progress against [`v0.md`](v0.md) and [`idea.md`](idea.md).  
> **Update this file** when layers ship or priorities change.  
> **Last reviewed:** 2026-06-21

---

## Summary

Alfred is **directionally aligned** with the v0 architecture: local-first, pluggable AI, Slack ingress, session memory, Markdown playbooks, read-only git investigation, JIRA, **AWS (Athena + CloudWatch + grade_events)**, Graphify, and observability with cost estimates.

| v0 first milestone | Status |
|--------------------|--------|
| `alfred init → configure AI → @alfred in Slack → read-only git investigation in a thread` | **Done** |
| `@alfred` JIRA ticket queries in thread | **Mostly done** |
| AWS read tools (Athena, CloudWatch, domain event tables) | **Done** — generic skill + playbook-driven `grade_events_query` |
| Small-company distributable product | **Partial** — Docker, admin UI, docs; git write ops still missing |

---

## Phase map (from v0 §7)

| Phase | Focus | Status | Notes |
|-------|--------|--------|-------|
| **0** | Scaffold, ABCs, config, `alfred init` | ✅ Done | Package, Pydantic config, encrypted secrets, `.alfred/` |
| **1** | AI plug layer | ✅ Done | Ollama, Anthropic, Gemini, Kimi; `LLMRouter`; per-task routing |
| **2** | Skills engine | 🟡 Partial | Bundled `skills/*.md`; playbooks; **no BM25 matcher** |
| **3** | Slack ingress | ✅ Mostly done | Socket Mode + `app_mention`; thinking status; custom `loading_messages`; **`alfred slack emojis`** |
| **4** | Thread context | 🟡 Partial | 30-day history, user names, git + JIRA blocks; **no relevancy ranking** |
| **5** | Investigation + ReAct + read tools | 🟡 Partial | Agent loop, git read, JIRA, Graphify, **AWS tools**; direct routes |
| **6** | Workflow skills (write git, governance) | ❌ Not started | JIRA update/create exist; no confirmation UX |
| **7** | AWS + admin UI | 🟡 Mostly done | Admin UI; **AWS Athena/CloudWatch/grade_events**; STS health check |
| **8** | Distribution | 🟡 Partial | Dockerfile + compose; README; ECS/EC2 patterns |

**Legend:** ✅ Done · 🟡 Partial · ❌ Not started

---

## Layer-by-layer

### Layer 1 — Ingress

| Component | Status | Location |
|-----------|--------|----------|
| `Task` model | ✅ | `backend/models/task.py` |
| Event sanitizer | ✅ | `backend/ingress/sanitize.py` |
| CLI `alfred exec` | ✅ | `backend/cli.py` |
| Slack `app_mention` | ✅ | `backend/slack/listener.py` |
| Slack DM / App Home Chat | ❌ | Needs `message.im` handler |
| GitHub App webhook | 🟡 | `backend/github/handler.py` — optional, needs public URL |
| HTTP enqueue queue | ❌ | Socket Mode for Slack |

### Layer 2 — Config & Admin

| Component | Status | Notes |
|-----------|--------|-------|
| `alfred init` | ✅ | Seeds config, secrets, example playbook |
| Encrypted secrets | ✅ | `ConfigManager` |
| Admin UI | ✅ | Chat, AI, Secrets, Integrations, Mirrors, Usage, Health |
| Health checks | 🟡 | Slack, Ollama, Git, JIRA, **AWS STS** |
| Observability | ✅ | Tokens, est. cost, tools, users |

### Layer 3 — Orchestration

| Component | Status | Notes |
|-----------|--------|-------|
| Task queue | ❌ | ABC only |
| Session store | ✅ | SQLite `(channel, thread_ts)` |
| Intent router | 🟡 | Keyword skill pick + direct paths (git, PR, JIRA, AWS investigation) |
| Git / JIRA session context | ✅ | `git_context.py`, `jira_context.py` |
| Identity map | ✅ | Slack ↔ JIRA ↔ GitHub bulk map |

### Layer 4 — Context engine

| Component | Status | Notes |
|-----------|--------|-------|
| Skill / playbook matcher | 🟡 | Keyword triggers |
| Slack thread + channel fetch | ✅ | 30-day default |
| Relevancy heuristics | ❌ | Full text dump |
| Repo context + Graphify | ✅ | Mirrors + optional graphs |
| Context policy | ✅ | `context_policy.py` |

### Layer 5 — AI layer

| Component | Status | Notes |
|-----------|--------|-------|
| LLM adapters | ✅ | OpenAI-compat, Anthropic, Gemini, Kimi |
| Per-task routing | ✅ | `skill_matching`, `investigation`, `workflow_execution` |
| Instrumentation | ✅ | Input/output tokens + est. USD |
| Synthesis on max steps | ✅ | `_synthesize_final_answer` |

### Layer 6 — Execution (tools)

| Component | Status | Notes |
|-----------|--------|-------|
| ReAct agent loop | ✅ | `backend/agent/loop.py` |
| Git API + read tools | ✅ | `git_api.py`, `git_local.py` |
| JIRA tools | ✅ | `jira_tool.py` |
| **AWS tools** | ✅ | `athena_query`, `cloudwatch_query`, `list_cloudwatch_log_groups`, `grade_events_query` |
| Graphify `query_graph` | 🟡 | When `graphify_enabled` |
| Git write tools | ❌ | |
| ECS / S3 direct tools | ❌ | Listed in `allowed_services` only |
| Structured UI payloads | ✅ | `grade_events_query`, `athena_query`, `jira_list`, `code_grep`, … |

### Layer 7 — Governance

| Component | Status | Notes |
|-----------|--------|-------|
| Skills + playbooks | ✅ | Generic skills in repo; company playbooks local |
| AWS guardrails | ✅ | grade_events LIMIT, partition windows, IAM error display |
| Policies / audit | ❌ | Observability events only |

---

## Shipped skills (`skills/`)

| Skill | Mode | Tools / purpose |
|-------|------|-----------------|
| `investigate_bug.md` | investigation | git read, get_pr, query_graph, … |
| `review_pr.md` | investigation | PR review + diff |
| `git_status.md` | workflow | list PRs, repos |
| `summarize_bugs.md` | conversational | Slack alert summaries |
| `jira_management.md` | investigation | JIRA CRUD + identity map |
| `jira_ticket.md` | investigation | Link PRs to JIRA |
| **`aws_query.md`** | investigation | athena_query, cloudwatch_query, list_cloudwatch_log_groups |

Company **investigation playbooks** (e.g. `grade_events`) → `.alfred/playbooks/` with `allowed_tools: [grade_events_query]`.

---

## What works today (user-visible)

- `@alfred` in Slack channels → in-thread reply with session memory
- Thinking status (Assistant API) with built-in + custom workspace emoji lines
- `alfred slack emojis` — list custom emoji shortcodes (needs `emoji:read`)
- Channel + thread history (30-day window)
- Domain playbooks from `.alfred/playbooks/`
- Git: PRs, review, grep/read/blame in mirrored repos
- JIRA: search/get/update/comment/create, assignee map, identity map
- **AWS: Athena SQL, CloudWatch Logs Insights, grade_events with guardrails**
- Structured Slack/UI rendering for AWS and grade_events results
- Graphify optional on sync
- Admin UI: Chat, Usage (cost), Health (incl. AWS STS)
- CLI: `exec`, `git sync`, `slack emojis`, `up` / `stop`, Ollama helpers
- GitHub App PR comment bot (optional)

---

## Known gaps (priority order)

1. **Slack DM / App Home Chat** — `message.im` handler + scopes
2. **Unified intent router** — replace growing `detect_*` direct routes
3. **Thread relevancy** — rank/filter messages before LLM
4. **Skill matcher** — BM25 or strict single-skill selection
5. **Git write ops** — checkout, cherry-pick, PR create (with confirmation)
6. **ECS / S3 tools** — beyond Athena/CloudWatch
7. **Task queue** — durable queue for crash recovery
8. **Full governance** — confirmation UX, audit export

---

## Architectural decisions

| Decision | Rationale |
|----------|-----------|
| Playbooks local, skills in repo | Generic tools ship with Alfred; company tables/rules stay private |
| Socket Mode | No public URL for Slack |
| Repo mirrors | Shared cache + per-session workspaces |
| Direct processor paths | PR/git/JIRA/AWS bypass weak models — temporary until unified router |
| AWS profile on host | Prefer IAM role/profile over static keys on EC2 |
| grade_events in playbooks | Table semantics are company-specific; tool enforces guardrails |
| Structured responses for AWS | UI card layout + LLM analysis text |

---

## Recommended next build steps

1. **Slack DMs** — `message.im` + document App Home Messages tab
2. **Entity cache** — persist resolved users/repos/issues per thread
3. **Thread relevancy** — v0 Phase 4 ranking pass
4. **Operational polish** — `users:read.email`, identity map, investigation routing to Kimi/Claude
5. Defer: Git 3 writes, ECS/S3 tools, BM25 matcher, task queue

---

## Doc hygiene

| Item | Action |
|------|--------|
| This file | Update when a phase/layer ships |
| [`README.md`](../../README.md) | User-facing setup — keep in sync |
| [`docs/playbooks/`](../playbooks/) | Example playbooks only; company playbooks local |
| `docs/playbooks/example-grade-events.md` | **Removed** — use local `.alfred/playbooks/` templates |

---

## References

- [`v0.md`](v0.md) — layer architecture
- [`idea.md`](idea.md) — original blueprint
- [`skills/`](../../skills/) — shipped skills
- Code: `backend/slack/listener.py`, `backend/ingress/processor.py`, `backend/tools/aws_tool.py`, `backend/aws/grade_events.py`
