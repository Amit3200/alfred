# Alfred Implementation Status

> **Living context file** for phased revamp. Update after each phase so the next session can continue without re-discovery.
>
> Architecture plan: [`routing-and-tools-plan.md`](routing-and-tools-plan.md) · Overview diagram: [`overview.md`](overview.md)

**Last updated:** 2026-08-05  
**Current phase:** Phase 4 complete

---

## Phase overview

| Phase | Focus | Status |
|-------|--------|--------|
| **0** | Tool structure, dedup, critical missing tools, grounding prompts | **Done** |
| **1** | Tool Planner, scoped tool binding, Slack read tools, config aliases | **Done** |
| **2** | GoalSpec, grounding gate, sync UI/API, subagent manifests | **Done** |
| **2b** | LangGraph orchestration (primary tool routing path) | **Done** |
| **3** | Repo doc index, structured formatters, SQLite checkpoint, plan-first routing | **Done** |
| **4** | Policy migration, plan templates, routing debugger, deprecate phrase routing | **Done** |

---

## Phase 4 — Policy migration + routing maturity

### Capability bundles

- `backend/routing/capabilities.py` — built-in bundles (`jira`, `google`, `repo`, …)
- Optional override: `.alfred/capabilities.yaml` (example: [`capabilities.example.yaml`](capabilities.example.yaml))
- `backend/routing/policies.py` — resolve tools/output format from bundle

### Playbook schema extensions

- Frontmatter: `type: policy | plan_template | workflow`
- Fields: `capability_bundle`, `plan_template`, `output.format`
- Parser: `backend/routing/playbooks.py`

### Plan templates

- `backend/routing/plan_templates.py` — trigger match → `ToolPlan`
- Hooked in `resolve_tool_plan()` after rules, before LLM
- Example: [`docs/playbooks/example-plan-template.md`](../playbooks/example-plan-template.md)
- Config: `routing.plan_template_min_confidence` (default 0.7)

### Deprecate phrase routing (investigation)

- `routing.phrase_routing_enabled: false` (default)
- `SkillRouter` skips keyword/heuristic/BM25 for investigation skills when off
- Conversational playbooks still use keyword triggers
- Plan-first + plan templates + optional LLM/skill-router fallback remain

### Routing debugger

- `backend/routing/trace_store.py` — `.alfred/routing_traces.json` (last 200)
- API: `GET /api/routing/traces`, `GET /api/routing/traces/{task_id}`, `GET /api/routing/capabilities`
- Admin UI: Configure → **Routing**
- Traces recorded from LangGraph runner via `TaskProcessor._record_routing_trace()`

### Multi-repo knowledge bases

- `git.repo_profiles[]` — per-repo role (`docs` | `code` | `scripts`) and flags (`doc_index`, `graphify`)
- `build_context_after_sync()` respects profiles: doc BM25 + Graphify extract per repo on sync
- API: `GET /api/repo-context/knowledge`, `POST .../sync|index|graphify` per repo
- Admin UI: **Knowledge → Knowledge bases** (sync / index / graph actions)
- `search_repo_docs` searches all indexed doc repos when `repo` omitted; optional `repo` arg per tool
- `query_graph` already accepts `repo` — Graphify rebuild on sync for profiled repos

### Sidebar (admin UI)

- **Setup** — profile, AI, secrets, integrations
- **Knowledge** — knowledge bases, repo mirrors, playbooks
- **Automation** — scripts, schedules
- **Developer** — tools, routing
- **Operations** — usage, logs, health

### Multi-repo doc index on sync (legacy default)

- Without profiles, all synced repos still get doc indexes when `repo_knowledge.index_on_sync: true`
- Main-repo overview manifest unchanged; Graphify defaults to `main_repo` unless profiled

---

## Phase 3 — Repo knowledge + routing maturity

### Repo doc index

- `backend/context/doc_index.py` — BM25 index over mirror docs + playbooks
- Docs-role repos (`git.repo_profiles` role=`docs`) index **all** `.md`/`.mdx` under the mirror; code repos use `repo_knowledge.doc_paths`
- Rebuilt on mirror sync when `repo_knowledge.index_on_sync: true`
- Tools: `search_repo_docs`, `read_repo_doc`, `list_repo_docs`
- Skill: `skills/repo_knowledge.md`
- Config: `repo_knowledge.*` in `backend/models/config.py`

### Structured formatters

- `backend/formatting/intent_formatters.py` — intent-class formatters
- `format_reply_node` in graph applies formatters before channel render

### SQLite LangGraph checkpoint

- `backend/orchestrator/graph/checkpoint.py` — persistent checkpointer at `.alfred/langgraph_checkpoints.db`
- Wired in `build.py` when `routing.langgraph_checkpoint: true`

### Plan-first routing

- `TaskProcessor._resolve_investigation_skill()` — tool plan + skill policy before SkillRouter
- Config: `routing.plan_first_routing: true`, `routing.skill_router_fallback: true`

### Script trigger routing

- `triggers:` field in `script.yaml` manifests
- `backend/integrations/company_scripts/triggers.py` — trigger index

---

## Phase 2b — LangGraph orchestration (summary)

All tool-routed investigation tasks flow through LangGraph when enabled (default **on**).

```
extract_entities → plan_tools → validate_plan
    → try_direct (fast path) OR run_worker (ReAct/Hermes)
    → validate_goal (grounding gate) → format_reply
```

---

## Optional follow-ups (not Phase 4)

- LangSmith export for graph traces
- Gemini token recording in streaming paths
- Skill linter CI for plan templates

---

## Verification

```bash
uv run pytest tests/test_phase4.py tests/test_phase3.py tests/test_langgraph_orchestration.py -q
uv run pytest -q
```

---

*Update this file at the end of each phase.*
