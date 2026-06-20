# Build Reference

These documents are the **planning and architecture references for building Alfred**. They are not runtime code — read them before implementing features or making structural decisions.

## Documents

| File | Description | Read when |
|------|-------------|-----------|
| [`idea.md`](idea.md) | Original V1 engineering blueprint — local-first agent, ABC interfaces, skill MD pattern, phased roadmap | Starting implementation; understanding core constraints |
| [`v0.md`](v0.md) | Expanded architecture evaluation — product vision, layer plan, Slack thread context, pluggable AI, build phases | Planning features; deciding what to build next |
| [`building_phase_v0.md`](building_phase_v0.md) | **Implementation status & gaps** vs v0 — what is done, partial, and missing | Before picking the next build task; keep updated as layers ship |

## Reading order

1. **`idea.md`** — baseline technical blueprint (queue, skills, ReAct loop, tool governance)
2. **`v0.md`** — product context, gaps in the blueprint, full layer architecture, revised phases
3. **`building_phase_v0.md`** — current code vs plan (living tracker)

## Relationship

- `idea.md` = *how to build the execution core*
- `v0.md` = *what to build and how the layers fit together* (extends and evaluates `idea.md`)
- `building_phase_v0.md` = *what we have built so far and what remains*

When code and docs diverge, update `building_phase_v0.md` first, then revise `v0.md` if the plan itself changes.

## Local-only files (gitignored)

Personal work while building Alfred — safe to delete anytime; not shared via git:

| Pattern / path | Use |
|----------------|-----|
| `scratch/` | Ideation plans, phase notes, experiments (e.g. `scratch/v0_ideation_phase1.md`, `scratch/building_phase_git.md`) |
| `*_ideation_*.md` | One-off ideation docs anywhere in this folder |
| `building_phase_*` except **`building_phase_v0.md`** | Scratch phase trackers |
| `*.html` | HTML exports for browser review |

**Tracked source of truth:** `idea.md`, `v0.md`, `building_phase_v0.md`. When a scratch plan ships, fold outcomes into `building_phase_v0.md` and delete the scratch file.
