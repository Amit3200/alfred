# Alfred — v0 Build Status & Gaps

> **Purpose:** Living tracker of implementation progress against [`v0.md`](v0.md) and [`idea.md`](idea.md).  
> **Update this file** when layers ship or priorities change.  
> **Last reviewed:** 2026-06-22

---

## Summary

Alfred is **directionally aligned** with the v0 architecture: local-first, pluggable AI, Slack ingress, session memory, **Markdown playbooks** for company rules, **read-only git investigation**, **JIRA ticket integration**, and **observability with cost estimates**.

We are past the early vertical slice — Phases 0–3, partial 4–5, partial 7–8 are shipped. Recent additions: **Graphify** code graphs, **usage cost tracking**, **JIRA tools + assignee resolution**, and **bulk Slack↔JIRA↔GitHub identity mapping**.

| v0 first milestone | Status |
|--------------------|--------|
| `alfred init → configure AI → @alfred in Slack → read-only git investigation in a thread` | **Done** — mirrors, local grep/read, PR review, agent loop, synthesis on max steps |
| `@alfred` JIRA ticket queries in thread | **Mostly done** — search/get/update/comment/create; assignee map + direct routes; polish and unified intent router remain |
| Small-company distributable product | **Partial** — Docker, admin UI, docs; AWS and write git still missing |

**Git commit baseline:** `9330dbf` — JIRA integration, assignee resolution, workspace identity mapping. Prior: `af924cd` — Graphify, usage cost, playbook routing, investigation fixes.

---

## Phase map (from v0 §7)

| Phase | Focus | Status | Notes |
|-------|--------|--------|-------|
| **0** | Scaffold, ABCs, config, `alfred init` | ✅ Done | Package, Pydantic config, encrypted secrets, `.alfred/` data dir |
| **1** | AI plug layer (`LLMProvider` + adapters) | ✅ Done | Ollama, Anthropic, Gemini, Kimi (OpenAI-compat); `LLMRouter`; per-task routing config |
| **2** | Skills engine (MD parser, matcher, tool registry) | 🟡 Partial | Bundled `skills/*.md` with `mode`, `allowed_tools`; JIRA skills added; **no BM25 matcher** |
| **3** | Slack ingress (mentions, queue, thread reply) | ✅ Mostly done | Socket Mode + `app_mention`; sanitize → `Task`; in-thread replies; thinking status |
| **4** | Thread context (fetch, relevancy, context bundle) | 🟡 Partial | Channel + thread history, user names, 30-day window; git + **JIRA context blocks**; **no relevancy ranking** |
| **5** | Investigation skill + read tools + ReAct loop | 🟡 Partial | Agent loop, git read tools, JIRA tools, Graphify `query_graph`; direct git/PR/jira/identity paths |
| **6** | Workflow skills (write git, governance, confirm) | ❌ Not started | JIRA update/create exist but no confirmation UX |
| **7** | AWS + admin UI | 🟡 Partial | Admin UI (Chat, Usage w/ cost, Repo mirrors, **JIRA** in Integrations/Health); **no AWS tools** |
| **8** | Distribution (Docker, docs, health) | 🟡 Partial | Dockerfile + compose; README setup guide; ECS/EC2 patterns documented |

**Legend:** ✅ Done · 🟡 Partial · ❌ Not started

---

## Layer-by-layer (v0 §3–§7)

### Layer 1 — Ingress

| Component | v0 spec | Current |
|-----------|---------|---------|
| `Task` model | Unified task from Slack/CLI/git | ✅ `backend/models/task.py` |
| Event sanitizer | Strip mentions, channel allowlist | ✅ `backend/ingress/sanitize.py` — includes `<@U\|name>` label extraction |
| CLI | `alfred exec` | ✅ `backend/cli.py` |
| Slack `app_mention` | Async ack, reply in thread | ✅ `backend/slack/listener.py` |
| Git webhooks | GitHub/GitLab ingress | 🟡 GitHub App `issue_comment` webhook (optional, needs public URL) |
| HTTP webhook + 3s ack queue | FastAPI enqueue pattern | ❌ Socket Mode for Slack; sync GitHub webhook handler |
| PR analysis ingress | PR URL / thread follow-up | ✅ `backend/ingress/pr_analysis.py`, `git_context.py` |

---

### Layer 2 — Config & Admin

| Component | v0 spec | Current |
|-----------|---------|---------|
| `alfred init` | Wizard / first-run setup | ✅ Seeds config, secrets, example playbook |
| `config.yaml` + encrypted secrets | Split plain vs secret config | ✅ `ConfigManager`; **JIRA** + `jira_api_token` |
| Web admin UI | Health, integrations, AI settings | ✅ Chat, AI, Secrets, Integrations (**Git, JIRA, GitHub App**), Repo mirrors, Usage |
| Health checks | Slack, Git, AWS, AI ping | 🟡 Slack, Ollama, git mirrors, **JIRA**; AWS config only |
| Channel allowlists | Per-integration | ✅ Slack `allowed_channels` |
| Observability | Token/tool/user tracking | ✅ Input/output tokens, **est. cost** (`observability/pricing.py`), Usage dashboard |

---

### Layer 3 — Orchestration

| Component | v0 spec | Current |
|-----------|---------|---------|
| Task queue | SQLite + in-memory `BaseQueue` | ❌ ABC only |
| Session store | `(channel_id, thread_ts)` keyed | ✅ SQLite `SessionStore` |
| Intent router | workflow vs investigation vs chit-chat | 🟡 Keyword skill pick + **direct paths** (git, PR, JIRA list, identity map) |
| Async worker | Dequeue → process → reply | 🟡 Per-mention thread in Slack listener |
| Git session context | Retry same PR, thread hints | ✅ `backend/ingress/git_context.py` |
| JIRA session context | Assignee resolution, project scope | ✅ `backend/ingress/jira_context.py` |

---

### Layer 4 — Context engine

| Component | v0 spec | Current |
|-----------|---------|---------|
| Skill matcher | BM25 / single skill load | 🟡 Keyword triggers on playbooks + skills |
| Slack thread fetcher | `conversations.replies` | ✅ |
| Channel history | Time-windowed fetch | ✅ 30-day default |
| Relevancy heuristics | Stack traces, URLs, recency | ❌ Full text dump; git hints only |
| Repo context | git grep, blame, index | ✅ Local mirrors + read tools + optional **Graphify** graphs |
| Context bundle | Structured bundle for agent | 🟡 `SlackContextBundle` + git + **JIRA** enrichment |
| Generic fetch policy | When to load channel vs thread | ✅ `context_policy.py` |
| Identity map | Slack ↔ JIRA ↔ GitHub | ✅ `build_workspace_identity_map`, `lookup_user_identity` |

---

### Layer 5 — AI layer

| Component | v0 spec | Current |
|-----------|---------|---------|
| `LLMProvider` ABC | `chat`, `stream`, optional `embed` | ✅ (`embed` not implemented) |
| Adapters | OpenAI-compat, Anthropic, Gemini, Kimi | ✅ |
| Config-driven switch | One key changes provider | ✅ |
| Per-task routing | cheap vs capable models | 🟡 `ai.routing.skill_matching`, `investigation`, `workflow_execution` |
| Instrumentation | Token/cost tracking | ✅ Per-event input/output tokens + **estimated USD** |
| Synthesis on max steps | Graceful answer when loop exhausted | ✅ `_synthesize_final_answer` in agent loop |

---

### Layer 6 — Execution (ReAct + tools)

| Component | v0 spec | Current |
|-----------|---------|---------|
| ReAct agent loop | Thought → tool → observation → repeat | ✅ `backend/agent/loop.py` (default 20 iterations) |
| Tool registry | Schema-defined, permission-gated | ✅ `backend/tools/registry.py` |
| Git API tools | list PRs, get PR, list repos | ✅ `backend/tools/git_api.py` |
| Git read tools | log, show, blame, grep, read_file | ✅ `backend/tools/git_local.py` |
| Graphify tools | Semantic code graph query | 🟡 `query_graph` when `git.graphify_enabled` |
| JIRA tools | search, get, update, comment, create, link | ✅ `backend/tools/jira_tool.py` |
| Identity tools | lookup user, workspace map | ✅ `lookup_user_identity`, `build_workspace_identity_map` |
| Repo mirrors | Clone-on-demand, session workspaces | ✅ `backend/git/mirror.py`, admin panel, CLI sync |
| Git write tools | checkout, cherry-pick, PR | ❌ |
| AWS read/write tools | CloudWatch, ECS, etc. | ❌ |
| Structured responses | Channel-rendered payloads | ✅ `pr_list`, `jira_list`, `code_grep`, … in `ResponsePayload` |

---

### Layer 7 — Governance

| Component | v0 spec | Current |
|-----------|---------|---------|
| Skill MD + YAML front matter | triggers, `allowed_tools`, mode | ✅ git + **JIRA** skills in `skills/` |
| Playbooks | Company formatting rules | ✅ `.alfred/playbooks/*.md` — **local only, not in git** |
| Policies | User allowlist, confirmation, audit | ❌ |
| Audit log | Every tool invocation | 🟡 Observability events (LLM + tools), not full governance audit |
| No company logic in core | Domain rules in MD | ✅ Enforced |

---

## Shipped skills (repo — safe to commit)

| Skill | Mode | Tools / purpose |
|-------|------|-----------------|
| `skills/investigate_bug.md` | investigation | grep_repo, read_file, git_log, git_blame, git_show, get_pr, query_graph, … |
| `skills/review_pr.md` | investigation | get_pr, get_pr_changes, grep_repo, read_file, … |
| `skills/git_status.md` | workflow | list_my_prs, list_prs, get_pr, list_repos |
| `skills/summarize_bugs.md` | conversational | Alerts/incidents operational report (Slack context only) |
| `skills/jira_management.md` | investigation | jira_search, get/update/comment/create issue, identity map tools |
| `skills/jira_ticket.md` | investigation | Link GitHub PRs to JIRA issues |

Company-specific **playbooks** live in `.alfred/playbooks/` (gitignored). Copy from `docs/playbooks/example-slack-summaries.md`.

---

## What works today (user-visible)

- `@alfred` in Slack → in-thread AI reply with session memory
- Channel + thread history (30-day window, reaction display names)
- Domain playbooks (local `.alfred/playbooks/`) matched by trigger keywords
- Git: open PRs, PR summary, **PR review with diffs**, repo grep/read/blame in mirrored repos
- Thread follow-ups: “check that PR again”, “where is X handled?” with session git context
- **JIRA:** list/search tickets, get issue, update/comment/create, assignee from `@mentions`, workspace identity map
- **Graphify:** optional semantic code graphs on sync (`query_graph` during investigation)
- Admin UI: Chat, secrets, AI routing, **JIRA** integr., Repo mirrors, **Usage** (input/output tokens, est. cost)
- CLI: `alfred exec`, `alfred git sync|workspaces|cleanup`, `alfred up` / `alfred stop`
- Kimi (Moonshot) as investigation provider option
- GitHub App: `@alfred review` on PR comments (optional, needs tunnel)

---

## Known gaps (priority order)

1. **Unified intent router** — replace growing set of `detect_*` direct routes with structured intent + entity cache
2. **Git 2 polish** — loop timeouts, Slack formatting cleanup, weak local model fallbacks
3. **Thread relevancy** — rank/filter messages before LLM (stack traces, links, recency)
4. **Skill matcher** — BM25 or strict single-skill selection
5. **Slack email scope** — document/enforce `users:read.email` for identity maps (emails blank without it)
6. **Task queue** — durable queue if moving off Socket Mode or needing crash recovery
7. **Git 3 write ops** — checkout, cherry-pick, PR create (with confirmation)
8. **AWS tools + health** — Phase 7
9. **Full governance** — confirmation UX, write-op policies, audit export

---

## Architectural decisions (since v0 was written)

| Decision | Rationale |
|----------|-----------|
| **Playbooks local, skills in repo** | Generic investigation/review/JIRA skills ship with Alfred; company rules stay in `.alfred/playbooks/` |
| **Playbooks** alongside skills | MD-driven domain rules without waiting for full skill engine |
| **Socket Mode** | No public URL for Slack; simpler local/EC2 deploy |
| **Repo mirrors** | Shared cache + per-session workspaces under `.alfred/repos/` |
| **Direct processor paths** | PR / git / JIRA / identity bypass weak models when intent is clear — **temporary** until unified router |
| **`assignee_map` + identity tools** | Slack `@mentions` don't survive sanitization; bulk map seeds config for efficient JQL |
| **Observability in SQLite** | Interaction events + input/output tokens + est. cost for Usage dashboard |
| **Graphify optional** | Heavy extraction on sync; gated by `git.graphify_enabled` |

---

## Recommended next build steps

1. **Operational config** — `git.default_org`, JIRA site/project, `assignee_map` from workspace identity run; route investigation to Kimi/Claude
2. **Slack scope** — add `users:read.email`, reinstall app, re-run identity map
3. **Entity cache** — persist resolved users/repos/issues per thread (reduce direct-route sprawl)
4. **Thread relevancy** — v0 Phase 4 ranking pass
5. Defer: Git 3 writes, AWS, BM25 matcher, task queue

---

## Doc hygiene

| Item | Action |
|------|--------|
| [`v0.md`](v0.md) header | Updated — points to this file for implementation status |
| This file | Update when a phase/layer ships |
| [`README.md`](../../README.md) | User-facing setup — keep in sync with Integrations (JIRA, Graphify, scopes) |
| `docs/build-reference/scratch/` | Local trackers (gitignored) |
| HTML exports in `docs/build-reference/` | Local only — gitignored |

---

## References

- [`v0.md`](v0.md) — full layer architecture and phase plan
- [`idea.md`](idea.md) — original blueprint
- [`docs/playbooks/`](../playbooks/) — playbook format + example (copy to `.alfred/playbooks/`)
- [`skills/`](../../skills/) — shipped skill templates
- Code entrypoints: `backend/slack/listener.py`, `backend/ingress/processor.py`, `backend/agent/loop.py`, `backend/jira/api.py`, `backend/ingress/user_identity.py`
