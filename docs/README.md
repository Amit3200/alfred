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

## Current status (2026-06-22)

**Shipped (v0):** Slack channel `@mentions`, git mirrors + PR review, JIRA, AWS (Athena/CloudWatch/grade_events), Graphify, observability, GitHub PR bot (with public URL), custom Slack thinking status, Admin UI & API authentication, modern Theme 2.0 aesthetics.

**Next (v0.1):** Unified intent router, thread relevancy, skill/playbook matcher upgrade.

**Later:** v1 — task queue, HTTP enqueue, governance · v2 — git writes, ECS/S3 tools · **Won't do:** Slack DMs.

Roadmap detail: [`building_phase_v0.md`](build-reference/building_phase_v0.md)

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
