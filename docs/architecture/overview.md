# Alfred Architecture Overview

> **Living diagram** for the routing revamp (Phases 0–4).  
> Detailed plan: [`routing-and-tools-plan.md`](routing-and-tools-plan.md) · Progress: [`implementation-status.md`](implementation-status.md)  
> Request entities + flow: [`request-processing.md`](request-processing.md)

**Last updated:** 2026-08-05

---

## System context

```mermaid
flowchart TB
    subgraph Ingress["Ingress"]
        Slack["Slack @mentions"]
        UI["Admin UI / CLI"]
    end

    subgraph Core["Alfred core (.alfred/ local data)"]
        Queue[("SQLite task queue")]
        Worker["Task worker"]
        Config["config.yaml + secrets"]
        Playbooks[".alfred/playbooks/"]
        Capabilities["capabilities.yaml (optional)"]
        Traces["routing_traces.json"]
    end

    subgraph Intelligence["Routing & orchestration"]
        Planner["Tool planner\nrules → plan templates → LLM"]
        Policy["Policy layer\nskill + capability bundle"]
        Graph["LangGraph pipeline"]
        Ground["Grounding gate"]
    end

    subgraph Tools["Tool registry"]
        Git["Git mirrors + Graphify"]
        Jira["JIRA"]
        Google["Google Workspace"]
        SlackT["Slack read"]
        AWS["Athena / CloudWatch"]
        Scripts["Company scripts"]
        Docs["Repo doc index (BM25)"]
    end

    Slack --> Queue
    UI --> Queue
    Queue --> Worker
    Worker --> Planner
    Playbooks --> Planner
    Capabilities --> Policy
    Planner --> Policy
    Policy --> Graph
    Graph --> Tools
    Graph --> Ground
    Ground --> Slack
    Ground --> UI
    Graph --> Traces
    Config --> Tools
```

---

## Investigation request flow (Phase 4)

```mermaid
sequenceDiagram
    participant U as User
    participant W as Worker
    participant P as Tool planner
    participant T as Plan templates
    participant S as Policy / skill
    participant G as LangGraph
    participant R as Tool registry

    U->>W: @alfred message
    W->>P: extract entities + resolve plan
    P->>P: rules (high confidence)
    alt rules miss
        P->>T: match plan_template triggers
    end
    alt still low confidence
        P->>P: LLM planner fallback
    end
    P->>S: map tools → policy skill / bundle
    S->>G: scoped tools + goal spec
    G->>R: direct path or ReAct worker
    R-->>G: tool results + trace
    G->>G: grounding gate + formatter
    G-->>U: Slack thread reply
```

LangGraph nodes:

```
extract_entities → plan_tools → validate_plan
  → try_direct | run_worker → validate_goal → format_reply
```

State persists to `.alfred/langgraph_checkpoints.db` when `routing.langgraph_checkpoint: true`.

---

## Routing tiers (investigation)

| Tier | Default | Role |
|------|---------|------|
| **Plan-first** | On | Rules + plan templates → policy skill |
| **Phrase routing** | **Off** | Keyword / heuristic / BM25 skill router (legacy) |
| **Skill router LLM** | Fallback | When plan-first misses and `skill_router_fallback: true` |
| **Conversational playbooks** | On | Keyword triggers still apply for `mode: conversational` |

Set `routing.phrase_routing_enabled: true` to restore investigation keyword routing.

---

## Capability bundles

Domain tool groups live in code (`backend/routing/capabilities.py`) with optional overrides in `.alfred/capabilities.yaml`.

| Bundle | Policy skill | Example tools |
|--------|--------------|---------------|
| `jira` | `jira_management` | `jira_search`, `get_jira_issue`, … |
| `google` | `google_workspace` | Sheets + Docs |
| `slack_read` | `summarize_bugs` | `slack_fetch_thread`, … |
| `repo` | `investigate_bug` | `grep_repo`, `query_graph`, … |
| `repo_docs` | `repo_knowledge` | `search_repo_docs`, … |
| `script` | `investigate_bug` | `run_company_script` |
| `aws` | `aws_query` | `athena_query`, … |

Policies (`type: policy` in playbooks) reference a bundle instead of duplicating long `allowed_tools` lists.

---

## Repo knowledge (multi-repo)

On `alfred git sync`:

- **All successfully synced repos** → doc BM25 index rebuild (`repo_knowledge.index_on_sync`)
- **Main repo only** → overview manifest + Graphify extraction (when enabled)

Tools: `search_repo_docs`, `read_repo_doc`, `list_repo_docs`, `query_graph`.

---

## Admin surfaces

| Panel | Path | Purpose |
|-------|------|---------|
| Tools | Configure → Tools | Full tool catalog + governance |
| Routing | Configure → Routing | Recent intent → plan → graph traces |
| Usage | Configure → Usage | Token usage + task checkpoints |

API: `GET /api/routing/traces`, `GET /api/routing/capabilities`, `GET /api/tools/catalog`.

---

## Key modules

| Module | Role |
|--------|------|
| `backend/routing/tool_planner.py` | Rules + templates + LLM planning |
| `backend/routing/plan_templates.py` | Trigger → structured `ToolPlan` |
| `backend/routing/capabilities.py` | Bundle definitions |
| `backend/routing/policies.py` | Resolve tools from bundle |
| `backend/routing/trace_store.py` | Routing debugger persistence |
| `backend/orchestrator/graph/` | LangGraph orchestration |
| `backend/context/doc_index.py` | Repo documentation BM25 index |

---

*Update alongside [`implementation-status.md`](implementation-status.md) when architecture changes.*
