# Alfred Documentation

Planning and reference materials for Alfred.

| Folder | Purpose |
|--------|---------|
| [`architecture/`](architecture/) | Routing revamp diagrams, phase status, capabilities example |
| [`playbooks/`](playbooks/) | **Example** playbooks — copy into `.alfred/playbooks/` locally (**never commit** company playbooks) |
| [`build-reference/`](build-reference/) | Blueprints, v0 plan, and implementation tracker |
| [`guides/`](guides/) | Operator how-tos (Slack boards, HTML slides) |
| [`scripts/`](scripts/) | Local + remote company script packages |

## Start here

| Audience | Read |
|----------|------|
| **What Alfred does (HTML)** | [`index.html`](index.html) — product deck; host on GitHub Pages from `docs/` |
| **Getting started** | [`README.md`](../README.md#getting-started) — clone, run, Slack, first `@alfred` |
| **Operators / new installs** | [`README.md`](../README.md) — setup, CLI, AWS, Slack, **scripts**, **logs** |
| **Company scripts** | [`scripts/README.md`](scripts/README.md) (local) · [`scripts/remote-repo.md`](scripts/remote-repo.md) (Git repo + venv) |
| **HTML slides** | [`guides/html-slides-artifacts.md`](guides/html-slides-artifacts.md) |
| **Slack List boards** | [`guides/slack-board-setup.md`](guides/slack-board-setup.md) — channel binding, tasks, JIRA vs List |
| **Architecture (current)** | [`architecture/overview.md`](architecture/overview.md) — context diagram + LangGraph flow |
| **Implementation progress** | [`architecture/implementation-status.md`](architecture/implementation-status.md) |
| **Routing/tools revamp spec** | [`architecture/routing-and-tools-plan.md`](architecture/routing-and-tools-plan.md) |
| **Contributors picking next work** | [`build-reference/building_phase_v0.md`](build-reference/building_phase_v0.md) |
| **Original layer design** | [`build-reference/v0.md`](build-reference/v0.md) |

## Current status (2026-10-18)

**Shipped (Phases 0–8 routing revamp + product surface):**

- Slack List boards, channel personas, JIRA create/update from thread
- Inbound connectors (Periskope WhatsApp → Slack List / JIRA)
- Repo docs Q&A with optional public doc URLs
- Web search, HTML slides, schedules, governance

- Tool planner (rules + plan templates + LLM fallback)
- LangGraph orchestration (plan → validate → execute → ground → format)
- Capability bundles + policy layer on playbooks
- Plan templates in `.alfred/playbooks/` (`type: plan_template`)
- Plan-first investigation routing; phrase routing **off by default**
- Repo doc BM25 index + multi-repo index on sync
- Tools catalog API/CLI + Admin **Tools** panel
- Routing trace store + Admin **Routing** debugger panel
- SQLite LangGraph checkpoints

**Optional follow-ups:** LangSmith export, Graphify on all repos on sync, skill linter CI.

**Won't do:** Slack DMs / App Home Chat.

Full gap analysis and build sequence: [`building_phase_v0.md`](build-reference/building_phase_v0.md)

### What to commit vs keep local

| Commit | Don't commit |
|--------|----------------|
| `building_phase_v0.md`, `v0.md`, `idea.md`, `README.md` | `building_phase_v0.html` and other `**/*.html` in build-reference |
| Example playbooks in `docs/playbooks/` | `.alfred/` (secrets, company playbooks, mirrors) |
| `docs/architecture/capabilities.example.yaml` | `.alfred/capabilities.yaml` (local overrides) |
| | `docs/build-reference/scratch/`, scratch `building_phase_*` files |

## Playbooks

- Generic example: [`playbooks/example-slack-summaries.md`](playbooks/example-slack-summaries.md)
- Plan template example: [`playbooks/example-plan-template.md`](playbooks/example-plan-template.md)
- Format guide: [`playbooks/README.md`](playbooks/README.md)
- Company-specific tables (e.g. event dumps) → create locally in `.alfred/playbooks/` — not in this repo

## Build reference

See [`build-reference/README.md`](build-reference/README.md) for reading order (`idea.md` → `v0.md` → `building_phase_v0.md`).
