# Build Reference

Planning and architecture references for Alfred — not runtime code.

## Documents

| File | Description | Read when |
|------|-------------|-----------|
| [`idea.md`](idea.md) | Original engineering blueprint | Understanding core constraints |
| [`v0.md`](v0.md) | Expanded architecture, layers, phases | Planning features |
| [`building_phase_v0.md`](building_phase_v0.md) | **Implementation status & gaps** | Before picking the next task |

## Reading order

1. **`idea.md`** — queue, skills, ReAct loop, tool governance
2. **`v0.md`** — product context, layer architecture
3. **`building_phase_v0.md`** — current code vs plan (living tracker)

When code and docs diverge, update **`building_phase_v0.md`** first, then **[`README.md`](../../README.md)**.

## Recently completed (2026-06)

- **AWS integration** — Athena, CloudWatch Logs, `grade_events_query` with guardrails
- **Structured UI** — grade events cards, AWS table views in admin Chat
- **Slack status** — custom workspace emoji `loading_messages`, `alfred slack emojis` CLI
- JIRA integration, identity map, Graphify, usage cost tracking, GitHub App PR ingress

## Local-only files (gitignored)

| Pattern | Use |
|---------|-----|
| `scratch/` | Ideation, phase notes |
| `building_phase_*` except **`building_phase_v0.md`** | Scratch trackers |
| `*.html` | HTML exports |

**Tracked source of truth:** `idea.md`, `v0.md`, `building_phase_v0.md`, [`README.md`](../../README.md).
