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

## Current status (2026-06-21)

**Shipped:** Slack ingress, session memory, git mirrors + PR review, JIRA tools, identity mapping, Graphify, observability/cost, **AWS Athena + CloudWatch + grade_events**, structured UI for query results, custom Slack thinking status, `alfred slack emojis`.

**Pending:** Git write ops, Slack DMs (App Home Chat), ECS/S3 tools, BM25 skill matcher, thread relevancy, unified intent router, durable task queue, full governance.

Full tracker: [`building_phase_v0.md`](build-reference/building_phase_v0.md)

## Playbooks

- Generic example: [`playbooks/example-slack-summaries.md`](playbooks/example-slack-summaries.md)
- Format guide: [`playbooks/README.md`](playbooks/README.md)
- Company-specific tables (e.g. event dumps) → create locally in `.alfred/playbooks/` — not in this repo

## Build reference

See [`build-reference/README.md`](build-reference/README.md) for reading order (`idea.md` → `v0.md` → `building_phase_v0.md`).
