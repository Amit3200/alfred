# Alfred Documentation

Planning and reference materials for Alfred.

| Folder | Purpose |
|--------|---------|
| [`playbooks/`](playbooks/) | **Example** playbooks — copy into `.alfred/playbooks/` locally (**never commit** company playbooks) |
| [`build-reference/`](build-reference/) | Blueprints, v0 plan, and implementation tracker |

## Start here

| Audience | Read |
|----------|------|
| **Operators / new installs** | [`README.md`](../README.md) — setup, CLI, AWS, Slack |
| **Contributors picking next work** | [`build-reference/building_phase_v0.md`](build-reference/building_phase_v0.md) |
| **Architecture deep dive** | [`build-reference/v0.md`](build-reference/v0.md) |

## Current status (2026-07-18)

**Shipped (v0):** Slack channel `@mentions`, git mirrors + PR review, JIRA, AWS (Athena/CloudWatch), Graphify, Google Workspace (Sheets/Docs), cron schedules, observability + task checkpoints, GitHub PR bot (with public URL), Admin UI & API authentication, planning mode, self-learning playbooks.

**Shipped (v0.1):** SQLite task queue + background worker, unified direct-action router (`detect_direct_action`), keyword + heuristic + LLM skill routing, context pruning (stack traces / long URLs), checkpoint timeline in Admin UI.

**Next (recommended order):**

| Priority | Target | Focus |
|----------|--------|--------|
| 1 | **v1** | Governance — audit log, confirmation UX, write policies (gate JIRA/Google writes too) |
| 2 | **v0.2 polish** | Thread relevancy ranking, BM25 playbook matcher |
| 3 | **v2** | Git write tools + `deploy_hotfix` workflow skill; ECS/S3 read tools |
| — | **Ops** | Self-learning playbook review gate, schedule UX polish, doc/test hardening |

**Won't do:** Slack DMs / App Home Chat.

Full gap analysis and build sequence: [`building_phase_v0.md`](build-reference/building_phase_v0.md)

### What to commit vs keep local

| Commit | Don't commit |
|--------|----------------|
| `building_phase_v0.md`, `v0.md`, `idea.md`, `README.md` | `building_phase_v0.html` and other `**/*.html` in build-reference |
| Example playbooks in `docs/playbooks/` | `.alfred/` (secrets, company playbooks, mirrors) |
| | `docs/build-reference/scratch/`, scratch `building_phase_*` files |

## Playbooks

- Generic example: [`playbooks/example-slack-summaries.md`](playbooks/example-slack-summaries.md)
- Format guide: [`playbooks/README.md`](playbooks/README.md)
- Company-specific tables (e.g. event dumps) → create locally in `.alfred/playbooks/` — not in this repo

## Build reference

See [`build-reference/README.md`](build-reference/README.md) for reading order (`idea.md` → `v0.md` → `building_phase_v0.md`).
