# Alfred — v0 Build Status & Gaps

> **Purpose:** Living tracker of implementation progress against [`v0.md`](v0.md) and [`idea.md`](idea.md).  
> **Update this file** when layers ship or priorities change.  
> **Last reviewed:** 2026-06-21

---

## Summary

Alfred is **directionally aligned** with the v0 architecture: local-first, pluggable AI, Slack ingress, session memory, and **Markdown-driven domain rules** (playbooks) instead of company-specific Python.

We are on an **early vertical slice** — roughly Phases 0–3 plus partial Phase 4 — not yet the full v0 demo (`@alfred` → read-only git investigation in a thread).

| v0 first milestone | Status |
|--------------------|--------|
| `alfred init → configure Ollama → @alfred in Slack → read-only git investigation in a thread` | **Partial** — Slack + Ollama + thread replies work; **git investigation and ReAct loop not built** |

---

## Phase map (from v0 §7)

| Phase | Focus | Status | Notes |
|-------|--------|--------|-------|
| **0** | Scaffold, ABCs, config, `alfred init` | ✅ Done | Package, Pydantic config, encrypted secrets, `.alfred/` data dir |
| **1** | AI plug layer (`LLMProvider` + adapters) | ✅ Done | Ollama (OpenAI-compat), Anthropic, Gemini; `LLMRouter`; config-driven provider switch |
| **2** | Skills engine (MD parser, matcher, tool registry) | 🟡 Partial | **Playbooks** (`.alfred/playbooks/*.md`) — triggers + body injected into prompt; no BM25 matcher, no `allowed_tools`, no tool registry |
| **3** | Slack ingress (mentions, queue, thread reply) | ✅ Mostly done | Socket Mode + `app_mention`; sanitize → `Task`; in-thread replies; thinking status via `assistant.threads.setStatus` |
| **4** | Thread context (fetch, relevancy, context bundle) | 🟡 Partial | Fetches channel + thread history, user display names, 30-day window; **no relevancy ranking**, stack-trace/PR heuristics, or linked-artifact resolution |
| **5** | Investigation skill + read tools + ReAct loop | ❌ Not started | Single-shot LLM chat only — no tools, no agent loop |
| **6** | Workflow skills (write git, governance, confirm) | ❌ Not started | |
| **7** | AWS + admin UI | 🟡 Partial | React admin UI, health table, Ollama setup, secrets save — **no AWS tools** |
| **8** | Distribution (Docker, docs, health) | 🟡 Partial | Dockerfile + compose exist; packaging/docs incomplete |

**Legend:** ✅ Done · 🟡 Partial · ❌ Not started

---

## Layer-by-layer (v0 §3–§7)

### Layer 1 — Ingress

| Component | v0 spec | Current |
|-----------|---------|---------|
| `Task` model | Unified task from Slack/CLI/git | ✅ `backend/models/task.py` |
| Event sanitizer | Strip mentions, channel allowlist | ✅ `backend/ingress/sanitize.py` |
| CLI | `alfred exec` | ✅ `backend/cli.py` |
| Slack `app_mention` | Async ack, reply in thread | ✅ `backend/slack/listener.py` (Socket Mode worker thread) |
| Git webhooks | GitHub/GitLab ingress | ❌ |
| HTTP webhook + 3s ack queue | FastAPI enqueue pattern | ❌ Using Socket Mode instead of `BaseQueue` |

**Gap:** No `BaseQueue` implementation; no git/web ingress handlers wired to `IngressHandler` ABC.

---

### Layer 2 — Config & Admin

| Component | v0 spec | Current |
|-----------|---------|---------|
| `alfred init` | Wizard / first-run setup | ✅ Seeds config, secrets, example playbook |
| `config.yaml` + encrypted secrets | Split plain vs secret config | ✅ `ConfigManager` |
| Web admin UI | Health, integrations, AI settings | ✅ `frontend/` + FastAPI routes |
| Health checks | Slack, Git, AWS, AI ping | 🟡 Slack + Ollama; Git/AWS config only |
| Channel allowlists | Per-integration | ✅ Slack `allowed_channels` |

**Gap:** Git/AWS health not fully exercised; no skill toggle UI.

---

### Layer 3 — Orchestration

| Component | v0 spec | Current |
|-----------|---------|---------|
| Task queue | SQLite + in-memory `BaseQueue` | ❌ ABC in `abstractions.py` only |
| Session store | `(channel_id, thread_ts)` keyed | ✅ SQLite `SessionStore` |
| Intent router | workflow vs investigation vs chit-chat | ❌ All messages → one `TaskProcessor` path |
| Async worker | Dequeue → process → reply | 🟡 Per-mention daemon thread in Slack listener |

**Gap:** No intent classification into skill modes; no durable task queue.

---

### Layer 4 — Context engine

| Component | v0 spec | Current |
|-----------|---------|---------|
| Skill matcher | BM25 / single skill load | 🟡 Playbooks: substring trigger match (may attach multiple) |
| Slack thread fetcher | `conversations.replies` | ✅ |
| Channel history | Time-windowed fetch | ✅ 30-day default; yesterday/today narrow windows |
| Relevancy heuristics | Stack traces, URLs, recency | ❌ Full text dump to model |
| Repo context | git grep, blame, index | ❌ Git config schema only |
| Context bundle | Structured `ContextBundle` for agent | 🟡 `SlackContextBundle` (text + raw messages + user names) |
| Generic fetch policy | When to load channel vs thread | ✅ `context_policy.py` (generic markers only) |

**Gap:** No thread message ranking; no repo/PR/commit resolution; no separate “cheap model” for context compression.

**Recent decision:** Removed domain-specific parsers (`alert_aggregator`, `merchant_alerts`, `channel_facts`). Summaries and formatting rules belong in **playbooks**, not Python.

---

### Layer 5 — AI layer

| Component | v0 spec | Current |
|-----------|---------|---------|
| `LLMProvider` ABC | `chat`, `stream`, optional `embed` | ✅ `backend/ai/base.py` (`embed` not implemented) |
| Adapters | OpenAI-compat, Anthropic, Gemini | ✅ |
| Config-driven switch | One key changes provider | ✅ |
| Per-task routing | cheap model for match, capable for investigation | ❌ Single `default_provider` |
| `max_tokens` / limits | Normalized across providers | 🟡 Set on OpenAI-compat (4096); not unified |

**Gap:** No routing config (`skill_matching` vs `investigation`); no embedding for skill match.

---

### Layer 6 — Execution (ReAct + tools)

| Component | v0 spec | Current |
|-----------|---------|---------|
| ReAct agent loop | Thought → tool → observation → repeat | ❌ |
| Tool registry | Schema-defined, permission-gated | ❌ |
| Git read tools | log, show, blame, grep, read_file | ❌ |
| Git write tools | checkout, cherry-pick, PR | ❌ |
| AWS read/write tools | CloudWatch, ECS, etc. | ❌ |
| Slack tools | post reply (beyond ingress) | ❌ |
| Max iterations / timeouts | Safety limits | ❌ |

**Gap:** Entire execution layer — this is the largest missing piece for the v0 demo.

---

### Layer 7 — Governance

| Component | v0 spec | Current |
|-----------|---------|---------|
| Skill MD + YAML front matter | triggers, `allowed_tools`, mode, governance | 🟡 Playbooks: `name`, `triggers`, `channels`, body |
| Skill directories | `skills/` + `skills/custom/` | 🟡 `.alfred/playbooks/` + `docs/playbooks/` examples |
| Policies | User allowlist, confirmation, audit | ❌ |
| Audit log | Every tool invocation | ❌ |
| No company logic in core | Domain rules in MD | ✅ Enforced — generic `context_policy`, no domain parsers |

**Gap:** Playbooks need to evolve into full **skills** (`mode`, `allowed_tools`, single-skill match, governance blocks).

---

## ABC interfaces (`backend/abstractions.py`)

| Interface | v0 V1 impl | Wired? |
|-----------|------------|--------|
| `BaseQueue` | SQLite + in-memory | ❌ Stub only |
| `StorageProvider` | SQLite sessions | 🟡 `SessionStore` exists but doesn't implement ABC |
| `LLMProvider` | Adapters | ✅ Separate module (`backend/ai/base.py`) |
| `IndexProvider` | BM25 skill match | ❌ Stub only |
| `IngressHandler` | Slack, CLI | ❌ Stub only; Slack/CLI implemented ad hoc |

---

## What works today (user-visible)

- `@alfred` in allowed Slack channels → in-thread AI reply
- Per-thread conversation memory (SQLite)
- Channel + thread Slack history (configurable window, user names on reactions)
- Domain playbooks from `.alfred/playbooks/*.md` matched by trigger keywords
- Admin UI: config, secrets, health, Ollama setup
- Local dev: `alfred serve --reload`, `alfred exec "…"`
- Generic prompts + Slack formatting (code-block tables, no markdown table breakage)

---

## Known gaps (priority order)

1. **ReAct agent loop** — tool call cycle in `TaskProcessor` (v0 Phase 5 blocker)
2. **Tool registry + read-only git tools** — `grep_repo`, `read_file`, `git_log`, etc.
3. **`investigate.md` skill** — first shipped skill with `mode: investigation` and tool allowlist
4. **Skill matcher** — BM25 or strict single-skill selection (v0 §4a; avoid loading multiple playbooks)
5. **Intent router** — workflow vs investigation vs conversational (v0 §3)
6. **Thread relevancy** — rank/filter messages before LLM (stack traces, links, recency)
7. **Task queue** — implement `BaseQueue` if moving to HTTP Events API or needing crash recovery
8. **Repo context** — local mirror / clone-on-demand for investigation
9. **Audit log + confirmation UX** — write ops and tool invocations
10. **AWS tools + health** — Phase 7
11. **Per-task model routing** — cheap local for match, capable cloud for investigation
12. **Git / webhook ingress** — beyond Slack + CLI

---

## Architectural decisions (since v0 was written)

| Decision | Rationale |
|----------|-----------|
| **Playbooks** instead of full skills (for now) | Ship MD-driven domain rules without tool infrastructure; matches v0 governance intent |
| **Removed domain parsers from core** | `alert_aggregator`, `merchant_alerts`, `channel_facts` deleted — company rules belong in playbooks |
| **Generic `context_policy`** | No product-specific keywords (FlexyPe, duplicate-order paths, etc.) |
| **Socket Mode** | Simpler local dev than public Request URL; differs from v0 HTTP ack + queue diagram |
| **Full context to model** | No truncation in Alfred; quality depends on model + playbooks + window size (30 days) |

---

## Recommended next build steps

Align with v0 §7 “first milestone”:

1. Extend playbook schema → **skill schema** (`mode`, `allowed_tools`, `requires_thread_context`)
2. Add **tool registry** + read-only git tools
3. Replace single-shot `processor.process()` chat with **ReAct loop** (max iterations, timeout)
4. Ship **`skills/investigate_bug.md`** (or equivalent in `.alfred/playbooks/`)
5. Add **thread relevancy** pass before building the LLM message list
6. Optional: wire `SessionStore` / queue to **`abstractions.py`** for cloud migration path

---

## Doc hygiene

| Item | Action |
|------|--------|
| [`v0.md`](v0.md) header says “No implementation started” | **Stale** — update when convenient |
| This file | Update when a phase/layer ships |
| HTML exports in `docs/build-reference/` | Local only — gitignored (see root `.gitignore`) |

---

## References

- [`v0.md`](v0.md) — full layer architecture and phase plan
- [`idea.md`](idea.md) — original blueprint (queue, skills, ReAct, governance)
- [`docs/playbooks/`](../playbooks/) — user-facing playbook format
- Code entrypoints: `backend/slack/listener.py`, `backend/ingress/processor.py`, `backend/ingress/playbooks.py`
