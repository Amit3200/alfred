# Build Reference

Planning and architecture references for Alfred — not runtime code.

## Documents

| File | Commit? | Description |
|------|---------|-------------|
| [`idea.md`](idea.md) | Yes | Original engineering blueprint |
| [`v0.md`](v0.md) | Yes | Expanded architecture, layers, phases |
| [`building_phase_v0.md`](building_phase_v0.md) | Yes | **Implementation status, gaps, roadmap (v0.1 / v1 / v2)** |
| `*.html`, `scratch/`, `building_phase_*` (except `v0.md`) | **No** | Gitignored — local exports and scratch notes |

## Reading order

1. **`idea.md`** — queue, skills, ReAct loop, tool governance
2. **`v0.md`** — product context, layer architecture
3. **`building_phase_v0.md`** — current code vs plan + **target release** per gap

When code and docs diverge, update **`building_phase_v0.md`** first, then **[`README.md`](../../README.md)**.

## Roadmap snapshot (2026-06-21)

| Target | Focus |
|--------|--------|
| **v0** | Slack channel ingress, git/JIRA/AWS read, GitHub PR bot (public URL), admin UI |
| **v0.1** | Intent router, thread relevancy, skill matcher upgrade |
| **v1** | HTTP enqueue queue, durable task queue, governance (confirmation + audit) |
| **v2** | Git write tools, ECS/S3 direct tools |
| **Won't do** | Slack DM / App Home Chat |

## Local-only files (gitignored)

| Pattern | Use |
|---------|-----|
| `**/*.html` | Markdown exports for browser (e.g. `building_phase_v0.html`) |
| `scratch/` | Ideation, phase notes |
| `building_phase_*` except **`building_phase_v0.md`** | Personal scratch trackers |

**Tracked source of truth:** `idea.md`, `v0.md`, `building_phase_v0.md`, [`README.md`](../../README.md).
