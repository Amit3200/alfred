# Alfred — v0 Build Status & Gaps

> **Purpose:** Living tracker of implementation progress against [`v0.md`](v0.md) and [`idea.md`](idea.md).  
> **Update this file** when layers ship or priorities change.  
> **Last reviewed:** 2026-06-21

---

## Summary

Alfred is **directionally aligned** with the v0 architecture: local-first, pluggable AI, Slack ingress, session memory, **Markdown playbooks** for company rules, and a **read-only git investigation** path.

We are past the early vertical slice — Phases 0–3, partial 4, and **partial Phase 5** (ReAct loop + git read tools) are shipped. Git mirror + PR review + thread follow-ups (Git 1b–1c) and observability are in the working tree.

| v0 first milestone | Status |
|--------------------|--------|
| `alfred init → configure AI → @alfred in Slack → read-only git investigation in a thread` | **Mostly done** — mirrors, local grep/read, PR review, agent loop; polish and relevancy ranking remain |

**Git commit baseline:** `5ec3935` — mirrors, PR review, session context, Kimi provider, mirror admin. Observability layer is implemented locally; confirm with `git log` before relying on this file alone.

---

## Phase map (from v0 §7)

| Phase | Focus | Status | Notes |
|-------|--------|--------|-------|
| **0** | Scaffold, ABCs, config, `alfred init` | ✅ Done | Package, Pydantic config, encrypted secrets, `.alfred/` data dir |
| **1** | AI plug layer (`LLMProvider` + adapters) | ✅ Done | Ollama, Anthropic, Gemini, Kimi (OpenAI-compat); `LLMRouter`; per-task routing config |
| **2** | Skills engine (MD parser, matcher, tool registry) | 🟡 Partial | Bundled `skills/*.md` with `mode`, `allowed_tools`; tool registry + allowlist; **no BM25 matcher**, playbooks still separate |
| **3** | Slack ingress (mentions, queue, thread reply) | ✅ Mostly done | Socket Mode + `app_mention`; sanitize → `Task`; in-thread replies; thinking status |
| **4** | Thread context (fetch, relevancy, context bundle) | 🟡 Partial | Channel + thread history, user names, 30-day window; **git thread hints** (PR retry, active PR); **no relevancy ranking** |
| **5** | Investigation skill + read tools + ReAct loop | 🟡 Partial | Agent loop, git read tools, direct git/PR/investigate paths; weak local models still unreliable for tool-calling |
| **6** | Workflow skills (write git, governance, confirm) | ❌ Not started | |
| **7** | AWS + admin UI | 🟡 Partial | Admin UI (Chat, Usage, Repo mirrors, health); **no AWS tools** |
| **8** | Distribution (Docker, docs, health) | 🟡 Partial | Dockerfile + compose; README setup guide; ECS/EC2 patterns documented |

**Legend:** ✅ Done · 🟡 Partial · ❌ Not started

---

## Layer-by-layer (v0 §3–§7)

### Layer 1 — Ingress

| Component | v0 spec | Current |
|-----------|---------|---------|
| `Task` model | Unified task from Slack/CLI/git | ✅ `backend/models/task.py` |
| Event sanitizer | Strip mentions, channel allowlist | ✅ `backend/ingress/sanitize.py` |
| CLI | `alfred exec` | ✅ `backend/cli.py` |
| Slack `app_mention` | Async ack, reply in thread | ✅ `backend/slack/listener.py` |
| Git webhooks | GitHub/GitLab ingress | ❌ |
| HTTP webhook + 3s ack queue | FastAPI enqueue pattern | ❌ Socket Mode instead of `BaseQueue` |
| PR analysis ingress | PR URL / thread follow-up | ✅ `backend/ingress/pr_analysis.py`, `git_context.py` |

---

### Layer 2 — Config & Admin

| Component | v0 spec | Current |
|-----------|---------|---------|
| `alfred init` | Wizard / first-run setup | ✅ Seeds config, secrets, example playbook |
| `config.yaml` + encrypted secrets | Split plain vs secret config | ✅ `ConfigManager` |
| Web admin UI | Health, integrations, AI settings | ✅ Chat, AI, Secrets, Integrations, **Repo mirrors**, **Usage**, Health |
| Health checks | Slack, Git, AWS, AI ping | 🟡 Slack, Ollama, git mirrors; AWS config only |
| Channel allowlists | Per-integration | ✅ Slack `allowed_channels` |
| Observability | Token/tool/user tracking | ✅ `backend/observability/`, Usage dashboard |

---

### Layer 3 — Orchestration

| Component | v0 spec | Current |
|-----------|---------|---------|
| Task queue | SQLite + in-memory `BaseQueue` | ❌ ABC only |
| Session store | `(channel_id, thread_ts)` keyed | ✅ SQLite `SessionStore` |
| Intent router | workflow vs investigation vs chit-chat | 🟡 Direct paths: PR analysis, git API, investigate, then agent loop |
| Async worker | Dequeue → process → reply | 🟡 Per-mention thread in Slack listener |
| Git session context | Retry same PR, thread hints | ✅ `backend/ingress/git_context.py` |

---

### Layer 4 — Context engine

| Component | v0 spec | Current |
|-----------|---------|---------|
| Skill matcher | BM25 / single skill load | 🟡 Keyword triggers on playbooks + skills; may attach multiple playbooks |
| Slack thread fetcher | `conversations.replies` | ✅ |
| Channel history | Time-windowed fetch | ✅ 30-day default |
| Relevancy heuristics | Stack traces, URLs, recency | ❌ Full text dump; git hints only |
| Repo context | git grep, blame, index | ✅ Local mirrors + read tools |
| Context bundle | Structured bundle for agent | 🟡 `SlackContextBundle` + git enrichment |
| Generic fetch policy | When to load channel vs thread | ✅ `context_policy.py` |

---

### Layer 5 — AI layer

| Component | v0 spec | Current |
|-----------|---------|---------|
| `LLMProvider` ABC | `chat`, `stream`, optional `embed` | ✅ (`embed` not implemented) |
| Adapters | OpenAI-compat, Anthropic, Gemini, Kimi | ✅ |
| Config-driven switch | One key changes provider | ✅ |
| Per-task routing | cheap vs capable models | 🟡 `ai.routing.skill_matching`, `investigation`, `workflow_execution` |
| Instrumentation | Token/cost tracking | ✅ `InstrumentedLLMProvider` → observability store |
| `max_tokens` / limits | Normalized across providers | 🟡 Partial |

---

### Layer 6 — Execution (ReAct + tools)

| Component | v0 spec | Current |
|-----------|---------|---------|
| ReAct agent loop | Thought → tool → observation → repeat | ✅ `backend/agent/loop.py` |
| Tool registry | Schema-defined, permission-gated | ✅ `backend/tools/registry.py` |
| Git API tools | list PRs, get PR, list repos | ✅ `backend/tools/git_api.py` |
| Git read tools | log, show, blame, grep, read_file | ✅ `backend/tools/git_local.py` |
| Repo mirrors | Clone-on-demand, session workspaces | ✅ `backend/git/mirror.py`, admin panel, CLI sync |
| Git write tools | checkout, cherry-pick, PR | ❌ |
| AWS read/write tools | CloudWatch, ECS, etc. | ❌ |
| Max iterations / timeouts | Safety limits | 🟡 Loop limits exist; needs hardening |

---

### Layer 7 — Governance

| Component | v0 spec | Current |
|-----------|---------|---------|
| Skill MD + YAML front matter | triggers, `allowed_tools`, mode | ✅ `skills/investigate_bug.md`, `review_pr.md`, `git_status.md` |
| Playbooks | Company formatting rules | ✅ `.alfred/playbooks/*.md` — **local only, not in git** |
| Policies | User allowlist, confirmation, audit | ❌ |
| Audit log | Every tool invocation | 🟡 Observability events (LLM + tools), not full governance audit |
| No company logic in core | Domain rules in MD | ✅ Enforced |

---

## Shipped skills (repo — safe to commit)

| Skill | Mode | Tools |
|-------|------|-------|
| `skills/investigate_bug.md` | investigation | grep_repo, read_file, git_log, git_blame, git_show, get_pr, list_repos |
| `skills/review_pr.md` | investigation | get_pr, get_pr_changes, grep_repo, read_file, … |
| `skills/git_status.md` | workflow | list_my_prs, list_prs, get_pr, list_repos |
| `skills/summarize_bugs.md` | conversational | alerts/incidents operational report (Slack context only) |

Company-specific **playbooks** live in `.alfred/playbooks/` (gitignored). Copy from `docs/playbooks/example-slack-summaries.md`.

---

## What works today (user-visible)

- `@alfred` in Slack → in-thread AI reply with session memory
- Channel + thread history (30-day window, reaction display names)
- Domain playbooks (local `.alfred/playbooks/`) matched by trigger keywords
- Git: open PRs, PR summary, **PR review with diffs**, repo grep/read/blame in mirrored repos
- Thread follow-ups: “check that PR again”, “where is X handled?” with session git context
- Admin UI: Chat, secrets, AI routing, **Repo mirrors**, **Usage** (tokens, tools, users)
- CLI: `alfred exec`, `alfred git sync|workspaces|cleanup`, `alfred up` / `alfred stop`
- Kimi (Moonshot) as investigation provider option

---

## Known gaps (priority order)

1. **Git 2 polish** — reliable investigation routing (capable model), loop timeouts, unified intent router, Slack formatting cleanup
2. **Thread relevancy** — rank/filter messages before LLM (stack traces, links, recency)
3. **Skill matcher** — BM25 or strict single-skill selection
4. **Playbooks → skills content** — hydrate company playbooks locally; expand generic skills in repo
5. **Task queue** — durable queue if moving off Socket Mode or needing crash recovery
6. **Git 3 write ops** — checkout, cherry-pick, PR create (with confirmation)
7. **AWS tools + health** — Phase 7
8. **Git / webhook ingress** — beyond Slack + CLI
9. **Full governance** — confirmation UX, write-op policies, audit export

---

## Architectural decisions (since v0 was written)

| Decision | Rationale |
|----------|-----------|
| **Playbooks local, skills in repo** | Generic investigation/review skills ship with Alfred; company alert formatting stays in `.alfred/playbooks/` (never committed) |
| **Playbooks** alongside skills | MD-driven domain rules without waiting for full skill engine |
| **Socket Mode** | No public URL for Slack; simpler local/EC2 deploy |
| **Repo mirrors** | Shared cache + per-session workspaces under `.alfred/repos/` |
| **Direct processor paths** | PR analysis / git API / investigate bypass weak models when intent is clear |
| **Observability in SQLite** | Interaction events for admin Usage dashboard; Slack user name cache |

---

## Recommended next build steps

1. **Operational config** — set `git.default_org`, route `ai.routing.investigation` to Kimi/Claude; smoke-test PR review + investigate in Slack
2. **Git 2 polish** — loop timeouts, intent router cleanup, formatting
3. **Thread relevancy** — v0 Phase 4 ranking pass
4. **Content** — company playbooks locally; refine shipped skills
5. Defer: Git 3 writes, AWS, BM25 matcher, task queue

---

## Doc hygiene

| Item | Action |
|------|--------|
| [`v0.md`](v0.md) header says “No implementation started” | **Stale** — update when convenient |
| This file | Update when a phase/layer ships |
| `docs/build-reference/scratch/` | Local trackers (gitignored) — e.g. `building_phase_git.md` |
| HTML exports in `docs/build-reference/` | Local only — gitignored |

---

## References

- [`v0.md`](v0.md) — full layer architecture and phase plan
- [`idea.md`](idea.md) — original blueprint
- [`docs/playbooks/`](../playbooks/) — playbook format + example (copy to `.alfred/playbooks/`)
- [`skills/`](../../skills/) — shipped skill templates
- Code entrypoints: `backend/slack/listener.py`, `backend/ingress/processor.py`, `backend/agent/loop.py`, `backend/git/mirror.py`
