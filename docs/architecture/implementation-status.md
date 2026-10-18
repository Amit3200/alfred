# Alfred Implementation Status

> **Living context file** for phased revamp. Update after each phase so the next session can continue without re-discovery.
>
> Architecture plan: [`routing-and-tools-plan.md`](routing-and-tools-plan.md) · Overview diagram: [`overview.md`](overview.md)  
> v2 tools/routing: [`tools-routing-v2-plan.md`](tools-routing-v2-plan.md) · Request flow: [`request-processing.md`](request-processing.md)

**Last updated:** 2026-08-17  
**Current phase:** Phase 8 done — processor package + hierarchical prompt routing. Next: MCP (v3) only if requested.

---

## Folder layout (tools + tests)

```
backend/tools/
  base/          # BaseTool, ToolContext, FunctionTool, ToolBundle, ToolChain
  builder.py     # build_tool_registry() — canonical registry builder
  catalog.py     # tool name sets + domains
  git/           # api, local, write, graphify
  jira/          # class tools + bundle
  slack/         # read + board class tools
  google/        # sheets + docs
  repo_docs/     # search / read / list
  schedule/      # cron job tools
  artifacts/     # HTML deck save / publish
  aws/ scripts/ web/

backend/domains/     # L2 — JiraService, SlackBoardService (+ board CRUD operations)
backend/integrations/ # L1 — HTTP/SDK only (Slack Lists client, JiraApiClient, …)
backend/routing/     # L4 — classifier, resolver, workflow_chain
  classifier/    # hierarchical prompt router (parent → function → capability)
  slack_board/ git/ jira/   # domain routing subpackages (old filenames deleted)

backend/orchestrator/processor/  # turn owner: core, session, direct, investigation, reply

tests/
  tools/<domain>/    # tool tests grouped by domain
  routing/           # planner, playbooks, classifier, workflow_chain
  orchestrator/      # processor, LangGraph, agent loop
  *.py               # API / UI / config / observability
```

Skills declare `workflow_chain` (composition metadata). Set `use_workflow_chain: true` only when that chain **is** the default plan (`html_slides`, `create_pr`, `repo_knowledge`). Mixed skills (JIRA, Slack board, schedule) keep the chain as a hint so “list tickets” is not forced through create→assign.

---

## Phase 5 — Class-based tools + AI capability routing (5c done)

> **Plan:** [`tools-routing-v2-plan.md`](tools-routing-v2-plan.md)

### Done (v2 Phase 1 + 2 + folder restructure)

- `BaseTool` / `ToolContext` / `FunctionTool` / `ToolBundle` / `ToolChain` — [`backend/tools/base/`](../../backend/tools/base/)
- `ToolRegistry.register_tool()` binds class tools
- **L2 domains:** `JiraService`, `SlackBoardService` in [`backend/domains/`](../../backend/domains/)
- **L3 class tools:** JIRA + Slack board (dedicated classes); Git, Google, AWS, scripts, web, Slack read, schedule, repo docs, artifacts via `FunctionTool` + bundles in [`discover.py`](../../backend/tools/base/discover.py)
- Closed intent enum + aliases: [`backend/routing/classifier/intent_classes.py`](../../backend/routing/classifier/intent_classes.py)
- **Hierarchical prompt router** (default **on**, `routing.classifier_enabled`): list enabled tool parents → fetch channel/board/entity metadata → pick parent → list that parent's functions → pick the best match. Rules are fallback only. [`hierarchical.py`](../../backend/routing/classifier/hierarchical.py)
- `resolve_turn()` → `TurnPlan` (capability + scoped tools + skill): [`resolver.py`](../../backend/routing/resolver.py)
- Processor uses `TurnPlan.prefers_jira` to skip Slack List direct handlers / board skill hijack
- Fine-grained capability bundles (`jira.write.create`, `slack.board.write.create`, `schedule.write.create`, …)
- Skills may declare `allowed_capabilities` (explicit `allowed_tools` still wins)
- Skill `workflow_chain` + `use_workflow_chain` → `ToolPlan(strategy="workflow_chain")`

### Not done (later)

- Optional thin `domains/git` and `domains/google`
- MCP client (v3) — **not implemented** (see below)

Details: [`tools-routing-v2-plan.md`](tools-routing-v2-plan.md) §13

---

## Phase 6 — Integrations hygiene (done)

- Slack List **CRUD verbs** live in [`backend/domains/slack_board/operations.py`](../../backend/domains/slack_board/operations.py). Tools and direct handlers call domain, not integrations.
- Board field defaults / ticket-detail text live in [`formatting.py`](../../backend/domains/slack_board/formatting.py) so `domains/` does not import `routing/`.
- Integrations keep HTTP: [`lists_client.py`](../../backend/integrations/slack/lists_client.py), [`list_fields.py`](../../backend/integrations/slack/list_fields.py). `board_service.py` is a thin resolve/field shim (does not import domains).
- Deleted empty leftover packages: `backend/{git,github,google,jira,slack,ollama}` (pycache only).

---

## Phase 7 — Routing subpackages (done)

Domain routing modules live under:

```
backend/routing/
  slack_board/   intent, direct, bootstrap, admin, agent, task_draft, prompt, llm_router
  git/           context, direct
  jira/          intent, context, direct
```

Old filenames (`slack_board_intent.py`, `git_direct.py`, `jira_intent.py`, `tools/git_api.py`, …) were **deleted**. Import the subpackages.

---

## Phase 8 — Processor split + hierarchical routing (done)

`TaskProcessor` lives in [`backend/orchestrator/processor/`](../../backend/orchestrator/processor/):

```
processor/
  core.py            # process / _process_task
  session.py         # load session, messages, governance
  direct.py          # workflow / PR / planned / repo-doc fast paths
  investigation.py   # skill + scoped tools + LangGraph/worker
  reply.py           # format / finish
  helpers.py         # STRUCTURED_TOOL_KINDS, tool-result → response
```

`from backend.orchestrator.processor import TaskProcessor` is unchanged.

### Hierarchical prompt routing

Primary classifier (`routing.classifier_enabled`, default **true**):

1. Gather query metadata (channel, Slack List DB binding, Jira project, session, entities)
2. Prompt: list enabled **tool parents** with descriptions → model picks one
3. Prompt: list that parent's **functions** (name + description) → model picks the best semantic match
4. Lift function → capability → `TurnPlan`

If the model is down or returns invalid JSON, deterministic rules run. A message that is essentially an issue key (`TECH-12`) skips the LLM (`entity_direct`). Ambiguous JIRA vs Slack List create is `conversational` (clarify, do not guess).

---

## MCP (v3) — not implemented

Internal tools use **MCP-shaped JSON Schema** (`BaseTool.schema()`), but Alfred does **not** speak the Model Context Protocol:

| Piece | Status |
|-------|--------|
| MCP client (`tools/list` / `tools/call` to external servers) | **Not built** |
| MCP config in `.alfred/config.yaml` / `AlfredConfig` | **None** |
| Admin UI for MCP servers | **None** |
| Alfred as an MCP server for other agents | **Not built** |
| Generic REST/OpenAPI connectors | **Not built** |

Third-party tools (Linear, Sentry, Datadog, …) still require a first-party Python client. Plan: [`tools-routing-v2-plan.md`](tools-routing-v2-plan.md) §8 and [`building_phase_v0.md`](../build-reference/building_phase_v0.md#v3--tool-extensibility-next-phase--not-started).

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
| **5** | Class-based tools, domain folders, `resolve_turn` / workflow chains | **5c done** |
| **6** | Slack List verbs in domain; delete empty leftover packages | **Done** |
| **7** | Routing subpackages (`slack_board/`, `git/`, `jira/`); old shims deleted | **Done** |
| **8** | Split `TaskProcessor`; hierarchical prompt routing as primary classifier | **Done** |

---

## Phase 4 — Policy migration + routing maturity

### Capability bundles

- `backend/routing/capabilities.py` — built-in bundles (`jira`, `google`, `repo`, …) plus operation-level keys (`jira.write.create`, …)
- Optional override: `.alfred/capabilities.yaml` (example: [`capabilities.example.yaml`](capabilities.example.yaml))
- `backend/routing/policies.py` — resolve tools/output format from bundle or `allowed_capabilities`

### Playbook schema extensions

- Frontmatter: `type: policy | plan_template | workflow`
- Fields: `capability_bundle`, `plan_template`, `output.format`, `allowed_capabilities`
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
- Enable evals for hierarchical parent→function routing in production

---

## Verification

```bash
uv run pytest tests/routing/test_phase5.py tests/routing/test_hierarchical_routing.py tests/routing/test_workflow_chain.py tests/routing/test_create_target_precedence.py tests/tools/jira/test_jira_tools.py tests/tools/test_tools_phase0.py tests/tools/git tests/tools/aws tests/tools/web tests/tools/scripts tests/routing/test_phase4.py tests/tools/schedule/test_scheduler.py -q
uv run pytest -q
```

---

*Update this file at the end of each phase.*
