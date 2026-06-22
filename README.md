# Alfred

**Alfred** is a local-first AI assistant for engineering teams. Install once, connect Slack and your stack, mirror repos, and `@alfred` answers in thread — with session memory, git investigation, PR review, JIRA, **AWS (Athena + CloudWatch)**, and company-specific **playbooks**.

Config and encrypted secrets live in `.alfred/` (not a SaaS). Optional Ollama on your machine; admin UI for setup, health, and usage tracking.

> **Status:** Alpha — Slack ingress, git mirrors, JIRA, AWS read tools, Graphify, observability, and pluggable AI (incl. Kimi) are working. Git write ops, Slack DMs, BM25 skill matching, and a unified intent router are still pending.  
> **Tracker:** [`docs/build-reference/building_phase_v0.md`](docs/build-reference/building_phase_v0.md) (last reviewed 2026-06-21)

**Requires Python 3.10+.** Local dev targets **Python 3.13** (see `.python-version`).

---

## Table of contents

- [Capabilities](#capabilities)
- [Not built yet](#not-built-yet)
- [Quick start](#quick-start)
- [Setup guide](#setup-guide)
- [AWS integration](#aws-integration)
- [Slack app](#slack-app)
- [CLI reference](#cli-reference)
- [Configuration](#configuration)
- [Project structure](#project-structure)
- [Architecture](#architecture)
- [Skills vs playbooks](#skills-vs-playbooks)
- [Example interactions](#example-interactions)
- [Deploy on AWS](#deploy-on-aws-hosting-alfred)
- [Development](#development)
- [Documentation](#documentation)

---

## Capabilities

| Area | What works |
|------|------------|
| **Slack `@alfred`** | Socket Mode in **channels** only (not app DM window). Thinking status + custom emoji lines. |
| **Session memory** | SQLite per `(channel, thread)` — follow-ups, active PR, last git action. |
| **Slack context** | Channel + thread history (~30 days), reaction display names, Slack Lists parsing. |
| **Git investigation** | Mirror repos; `grep_repo`, `read_file`, `git_log`, `git_blame`, `git_show`. |
| **PR review** | Summarize/review from URL or thread; GitHub App `@alfred review` on PR comments (optional, needs public URL). |
| **JIRA** | Search, get, update, comment, create, link PRs; assignee resolution via `assignee_map`; workspace identity map. |
| **AWS (read-only)** | `athena_query`, `cloudwatch_query`, `list_cloudwatch_log_groups`; domain **`grade_events_query`** via local playbooks with guardrails (LIMIT, partition windows). |
| **Graphify** | Optional code graphs on sync — `query_graph` when `git.graphify_enabled`. |
| **Playbooks** | `.alfred/playbooks/*.md` — company triggers, formatting, investigation tools (local only). |
| **Skills** | Bundled `skills/*.md` — investigate, review PR, git status, JIRA, AWS, summarize alerts. |
| **AI** | Ollama, OpenAI-compat, Anthropic, Gemini, Kimi — per-task routing (`investigation`, `skill_matching`, …). |
| **Admin UI** | Chat, secrets, AI routing, integrations, repo mirrors, usage (tokens + est. cost), health. |
| **CLI** | `exec`, `git sync`, `slack emojis`, `up` / `stop`, Ollama helpers. |

### Shipped skills (`skills/`)

| Skill | Purpose |
|-------|---------|
| `investigate_bug.md` | Code search, git read tools, PR context, Graphify |
| `review_pr.md` | PR diff review and summary |
| `git_status.md` | Open PRs, repo lists |
| `jira_management.md` | JIRA search/update/comment/create, identity map |
| `jira_ticket.md` | Link PRs to JIRA issues |
| `aws_query.md` | Athena + CloudWatch Logs (generic) |
| `summarize_bugs.md` | Operational summaries from Slack context |

Company-specific Athena tables (e.g. event dumps) → **`.alfred/playbooks/`** with `mode: investigation` and `allowed_tools`.

---

## Not built yet

| Item | Target | Notes |
|------|--------|--------|
| Intent router, thread relevancy, skill matcher | **v0.1** | Upgrade from keywords + direct paths |
| HTTP enqueue queue, durable task queue, governance | **v1** | Confirmation UX, audit export |
| Git write ops, ECS/S3 tools | **v2** | |
| Slack app DMs | **Won't do** | Use `@alfred` in channels |

Details: [`building_phase_v0.md`](docs/build-reference/building_phase_v0.md)

---

## Quick start

```bash
git clone <repo-url> alfred && cd alfred
chmod +x scripts/*.sh
./scripts/setup.sh          # venv, alfred init, example playbook
./scripts/up.sh             # API + Slack listener + Vite UI
```

| Service | URL |
|---------|-----|
| Admin UI (dev) | http://127.0.0.1:5173 |
| API + bundled UI | http://127.0.0.1:8080 |
| Health | http://127.0.0.1:8080/api/health |

```bash
alfred token      # view admin username, password, and token for login
alfred status     # init + Slack readiness
```

Then complete [Setup guide](#setup-guide) for Slack, AI, Git, and optional AWS/JIRA.

---

## Setup guide

### Prerequisites

- Python **3.13** (local) or Docker (production)
- Slack workspace admin (create app)
- AI provider API key (Kimi, Anthropic, OpenAI, or local Ollama)
- GitHub/GitLab token with repo read access
- Optional: JIRA Cloud, AWS IAM profile or keys for Athena/CloudWatch

### 1 — Install

**Local:**

```bash
./scripts/setup.sh
```

**Docker:**

```bash
docker compose up --build -d
docker compose logs alfred | grep -i token   # admin token on first boot
```

### 2 — Admin UI

Open http://127.0.0.1:5173 (dev) or http://127.0.0.1:8080 (serve). Log in using your admin username and password (run `alfred token` to retrieve them).

### 3 — Secrets (Admin → Secrets)

| Secret | Used for |
|--------|----------|
| Slack bot token (`xoxb-`) | Post replies, read history |
| Slack signing secret | Event verification |
| Slack app token (`xapp-`) | Socket Mode |
| AI API keys | LLM calls |
| Git token | Mirrors, PR API, GitHub comment reactions |
| JIRA API token | Ticket tools |
| AWS keys (optional) | Leave blank if using server-side `aws.profile` |
| GitHub webhook secret | PR comment bot |

Env fallbacks: [`.env.example`](.env.example)

### 4 — Slack app

See [Slack app](#slack-app). Then `/invite @alfred` in a channel and `@alfred hello`.

> **Note:** Alfred responds to **`@alfred` in channels**, not the app's Chat/DM tab (out of scope).

### 5 — AI (Admin → AI)

- Enable provider(s), set API keys
- Route **`investigation`** to a capable model (Kimi, Claude) — small Ollama models are weak at tool-calling
- Kimi: provider `kimi`, base `https://api.moonshot.ai/v1`, model `kimi-k2.6`

### 6 — Git (Admin → Integrations)

```yaml
git:
  enabled: true
  provider: github
  default_org: YourOrg
  main_repo: YourOrg/your-service
  graphify_enabled: false   # optional semantic graphs
```

```bash
alfred git sync
```

### 7 — JIRA (optional)

```yaml
jira:
  enabled: true
  base_url: https://yourorg.atlassian.net
  email: you@yourorg.io
  default_project: TECH
  assignee_map: {}   # populate via workspace identity map
```

### 8 — AWS (optional)

See [AWS integration](#aws-integration).

### 9 — Company playbooks

```bash
mkdir -p .alfred/playbooks
cp docs/playbooks/example-slack-summaries.md .alfred/playbooks/my-alerts.md
# add investigation playbooks for your Athena tables, alert bots, etc.
```

Never commit `.alfred/` — secrets, DB, mirrors, playbooks.

### 10 — Run

```bash
./scripts/up.sh      # dev: API + Slack + Vite
alfred serve         # production API only
alfred stop          # stop background processes
```

Logs: `.alfred/alfred.log`

### Verify

| Check | How |
|-------|-----|
| Health | Admin → Health (Slack, AI, Git, JIRA, AWS) |
| Chat | Admin → Chat |
| Slack | `@alfred what are my open PRs?` |
| Git | `@alfred where is X handled in org/repo?` |
| JIRA | `@alfred status of TECH-123` |
| AWS | `@alfred pull grade events for fp_id …` (with playbook + config) |
| Usage | Admin → Usage — tokens, est. cost, tools |

---

## AWS integration

Alfred includes **read-only** AWS tools via `pip install alfred-agent[aws]` (boto3).

### Tools

| Tool | Purpose |
|------|---------|
| `athena_query` | Run SQL against Glue/Athena |
| `cloudwatch_query` | Logs Insights on a log group or mapped service |
| `list_cloudwatch_log_groups` | Discover log group paths |
| `grade_events_query` | Guardrailed queries on a configured event table (via company playbook) |

IAM errors are surfaced with needed actions — Alfred does not guess credentials.

### Config (`config.yaml`)

```yaml
aws:
  enabled: true
  profile: your-profile          # server-side profile (preferred on EC2)
  region: ap-south-1
  allowed_services:
    - cloudwatch
    - athena
    - ecs
    - s3
  athena_database: your_glue_db
  athena_workgroup: primary
  athena_output_location: s3://your-bucket/athena/queries/
  log_group_map:
    checkout-api: /ecs/checkout-api
  grade_events_table: grade_events
  grade_events_s3_location: s3://your-data-bucket/path/   # documentation / validation
```

**Secrets:** optional `aws_access_key_id` / `aws_secret_access_key` in Admin → Secrets. Profile takes precedence when configured on the host.

### Domain event tables (playbooks)

Generic AWS querying is in `skills/aws_query.md`. **Company-specific tables** (partition columns, filter semantics, response format) belong in **`.alfred/playbooks/`**:

```yaml
---
name: grade_events
mode: investigation
triggers:
  - grade events
  - checkout events
allowed_tools:
  - grade_events_query
---
```

Document database, table, S3 path, partition keys (`date`, `hour`), and which IDs to filter on (`fp_id`, `session_id`, `merchant_id`).

### Health check

Admin → Health → **AWS** runs STS `GetCallerIdentity` when enabled.

---

## Slack app

Configure at [api.slack.com/apps](https://api.slack.com/apps):

1. Enable **Socket Mode** → App-Level Token with `connections:write`
2. **Bot Token Scopes:**  
   `app_mentions:read`, `channels:history`, `channels:read`, `chat:write`, `files:write`, `groups:history`, `groups:read`, `lists:read`, `users:read`, **`users:read.email`**, `assistant:write`  
   Optional: **`emoji:read`** (for `alfred slack emojis`)
3. Enable **Agents & AI Apps** for native thinking status
4. **Event Subscriptions** → `app_mention`
5. Install to workspace → paste tokens in Admin → Secrets

**Custom thinking status** — add workspace emoji lines in config:

```yaml
slack:
  loading_messages:
    - ":this_is_fine: Everything is fine. Checking prod…"
    - ":typingcat: Typing furiously…"
```

List shortcodes: `alfred slack emojis` (requires `emoji:read` scope). Custom + built-in lines are mixed randomly (10 per request).

**App Home Chat tab:** enable Messages tab in App Home if you want the input unblocked — Alfred still only processes channel `@mentions` until DM support ships.

---

## CLI reference

| Command | Description |
|---------|-------------|
| `alfred init` | Create `.alfred/`, config, encrypted secrets. Prompts interactively for admin credentials. |
| `alfred init --force` | Re-initialize (allows updating admin credentials) |
| `alfred serve` | API + admin UI + Slack listener |
| `alfred serve --reload` | Dev auto-reload |
| `alfred up` | Background: API + Slack (+ Vite UI, + Ollama if default) |
| `alfred stop` / `alfred down` | Stop background processes |
| `alfred status` | Data dir, init state, Slack readiness |
| `alfred token` | Print admin username, password, and token |
| `alfred exec "…"` | Run locally (no Slack post) |
| `alfred git sync` | Clone/update shared mirrors |
| `alfred git workspaces` | List session workspaces |
| `alfred git cleanup` | Remove expired workspaces |
| `alfred context generate` | Regenerate main-repo markdown context |
| `alfred slack emojis` | List workspace emoji shortcodes (`-q`, `--yaml`) |
| `alfred ollama status` | Ollama install/runtime |
| `alfred ollama setup` | Install, start, pull default model |
| `alfred ollama pull --model …` | Pull a model |
| `alfred ollama stop` | Stop Ollama |

Global: `--data-dir PATH` (default: `ALFRED_DATA_DIR` or `./.alfred`)

---

## Configuration

### `.alfred/` layout

| Path | Purpose |
|------|---------|
| `config.yaml` | Non-secret settings |
| `secrets.enc` | Encrypted tokens |
| `.key` | Local encryption key |
| `alfred.db` | Sessions + observability (SQLite) |
| `alfred.log` | Runtime logs |
| `playbooks/` | **Your** domain playbooks (gitignored) |
| `repos/shared/` | Git mirror cache |
| `repos/workspaces/` | Per-conversation workspaces |
| `cache/playbook_urls/` | Fetched live URL cache |

### Example routing snippet

```yaml
ai:
  default_provider: kimi
  routing:
    skill_matching: kimi
    investigation: kimi
git:
  enabled: true
  default_org: YourOrg
  main_repo: YourOrg/backend
jira:
  enabled: true
  base_url: https://yourorg.atlassian.net
  default_project: TECH
observability:
  user_labels: {}
  model_pricing: {}
```

Environment: [`.env.example`](.env.example) — `ALFRED_DATA_DIR`, `ALFRED_HOST`, `ALFRED_PORT`.

### Security & Authentication

To protect the admin UI and the API, Alfred enforces authentication across all API endpoints.

#### 1. Credentials Configuration
* **Interactive Initialization**: Running `alfred init` will prompt you for an admin username and password. If you leave the password blank, a secure password is auto-generated.
* **Non-Interactive / CI**: Use `alfred init --non-interactive` to automatically generate random secure credentials.
* **Custom Credentials**: You can specify custom credentials using `alfred init --username <username> --password <password>`.
* **Legacy Backfilling**: Starting an existing Alfred deployment without credentials automatically generates a secure admin username, password, and token, saving them in the encrypted secrets store.

#### 2. Authenticating API Calls
External integrations, CLI commands, or scripts talking to the Alfred API can authenticate in three ways:
* **HTTP Basic Auth**: Pass standard Basic Authentication using the admin username and password.
* **HTTP Bearer Auth**: Pass the admin token in the Authorization header (`Authorization: Bearer <token>`).
* **Custom Header**: Pass the admin token in the `X-Alfred-Token` header.

#### 3. Retrieving Credentials
To print your current admin username, password, and API token at any time, run:
```bash
alfred token
```


### Optional — GitHub PR comment bot

Requires a **public HTTPS URL** on your company subdomain (e.g. `alfred.flexype.dev` via Cloudflare tunnel or ALB). Configure GitHub App webhook → `/api/v1/github/webhook`, subscribe to `Issue comment`, install on org repos. Admin → Integrations → GitHub App + Secrets. Comment `@alfred review` on a PR.

### Optional — Public URL (Cloudflare Tunnel)

Only needed for GitHub webhooks or remote Admin UI — **not** for Slack (Socket Mode). Use `./scripts/tunnel.sh` after `cloudflared tunnel` setup. Local dev works with `./scripts/up.sh` alone.

---

## Project structure

```
alfred/
├── backend/
│   ├── agent/                 # ReAct loop
│   ├── ai/                    # LLM adapters, routing, instrumentation
│   ├── api/                   # FastAPI routes (health, chat, config, …)
│   ├── aws/                   # Session, Athena, CloudWatch, grade_events guardrails
│   ├── context/               # Repo context generator, Graphify
│   ├── git/                   # Mirrors, sandbox, GitHub/GitLab API
│   ├── github/                # GitHub App webhook handler
│   ├── ingress/               # Processor, playbooks, Slack/JIRA/git context, render
│   ├── jira/                  # JIRA Cloud REST client
│   ├── observability/         # Usage, pricing, tool events
│   ├── slack/                 # Socket Mode listener, status, emojis, files
│   ├── storage/               # SQLite sessions, Slack user cache
│   ├── tools/                 # Registry — git, jira, aws, graphify
│   ├── ollama/                # Local Ollama service helpers
│   ├── runtime/               # Process supervisor (up/stop)
│   ├── models/                # Pydantic config, task, response, session
│   ├── cli.py
│   ├── config_manager.py
│   └── health.py
├── frontend/                  # React admin UI (Vite)
├── skills/                    # Generic skills (committed)
├── docs/
│   ├── playbooks/             # Example playbooks + README
│   └── build-reference/       # Architecture + implementation tracker
├── tests/
├── scripts/                   # setup.sh, up.sh, dev.sh, tunnel.sh
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

Runtime data (not in git): **`.alfred/`** at repo root or `ALFRED_DATA_DIR`.

---

## Architecture

```mermaid
flowchart LR
    subgraph ingress [Ingress]
        Slack[Slack Socket Mode]
        CLI[alfred exec]
        GH[GitHub App webhook]
    end

    subgraph core [Core]
        Proc[TaskProcessor]
        PB[Playbooks]
        SK[Skills]
        SESS[Sessions]
    end

    subgraph exec [Execution]
        Direct[Direct routes]
        Agent[ReAct loop]
        Tools[Tools]
    end

    subgraph data [Data sources]
        Git[Repo mirrors]
        JIRA[JIRA Cloud]
        AWS[Athena + CloudWatch]
        GF[Graphify]
    end

    Slack --> Proc
    CLI --> Proc
    GH --> Proc
    Proc --> PB & SK & SESS
    Proc --> Direct & Agent
    Agent --> Tools
    Tools --> Git & JIRA & AWS & GF
    Proc --> AI[LLM router + observability]
```

Principles: **local-first**, **generic core + local playbooks**, **pluggable AI**, **read-only AWS/git by default**.

Full design: [`docs/build-reference/v0.md`](docs/build-reference/v0.md)

---

## Skills vs playbooks

| | **Skills** (`skills/`) | **Playbooks** (`.alfred/playbooks/`) |
|---|------------------------|--------------------------------------|
| Purpose | Generic investigation, review, JIRA, AWS | Company rules — alerts, tables, event dumps |
| Shipped with Alfred | Yes | No — you create locally |
| Commit to git? | **Yes** | **No** |
| Example | `skills/aws_query.md` | `my-alerts.md`, `grade-events.md` |

Format: [`docs/playbooks/README.md`](docs/playbooks/README.md)

---

## Example interactions

**Slack (channels):**

```
@alfred what are my open PRs?
@alfred review https://github.com/YourOrg/backend/pull/42
@alfred where is duplicate order handled in backend?
@alfred list my open TECH tickets
@alfred status of TECH-123
@alfred pull grade events for fp_id 019ee783-2bf1-76ab-a65d-f6f18a9272e7
@alfred query cloudwatch logs for checkout-api errors in the last hour
@alfred map all slack users to jira and github
```

**CLI:**

```bash
alfred exec "list open PRs on YourOrg/backend"
alfred git sync
alfred slack emojis --yaml
alfred slack emojis -q cat
```

---

## Deploy on AWS (hosting Alfred)

Alfred uses **Slack Socket Mode** (outbound WebSocket) — no public URL required for Slack. Outbound HTTPS to Slack, AI APIs, GitHub, and AWS is required.

### EC2

- Instance with 30+ GB EBS if mirroring many repos
- Security group: restrict `:8080` for Admin UI; allow outbound HTTPS
- `ALFRED_DATA_DIR=/data/.alfred` on persistent volume
- Docker or `alfred serve` with systemd / compose `restart: unless-stopped`
- Optional: attach IAM role for AWS tools instead of static keys

### ECS (Fargate)

- ECR image from `Dockerfile`
- EFS mount at `/data/.alfred` for secrets, DB, mirrors, playbooks
- Private subnet + NAT for outbound
- Optional ALB for Admin UI; not required for Slack
- Health: `GET /api/health`

### Docker Compose (any host)

```bash
docker compose up --build -d
```

Port `8080`, volume `alfred_data` → `/data/.alfred`.

---

## Development

```bash
source .venv/bin/activate
pip install -e ".[ai,dev,aws,slack]"
uv run pytest tests/ -q
ruff check backend tests
cd frontend && npm run dev
```

Release wheel: `./scripts/build-release.sh`

---

## Documentation

| Document | Description |
|----------|-------------|
| [`docs/README.md`](docs/README.md) | Docs index |
| [`docs/build-reference/building_phase_v0.md`](docs/build-reference/building_phase_v0.md) | **Implementation status & gaps** |
| [`docs/build-reference/v0.md`](docs/build-reference/v0.md) | Layer architecture |
| [`docs/build-reference/idea.md`](docs/build-reference/idea.md) | Original blueprint |
| [`docs/playbooks/README.md`](docs/playbooks/README.md) | Playbook format |

---

## Roadmap

| Target | Focus | Status |
|--------|--------|--------|
| **v0** | Slack channels, git/JIRA/AWS read, GitHub PR bot, admin UI | Mostly done |
| **v0.1** | Intent router, thread relevancy, skill matcher | Next |
| **v1** | Task queue, HTTP enqueue, governance | Planned |
| **v2** | Git writes, ECS/S3 tools | Planned |
| — | Slack DMs | **Won't do** |

Full tracker: [`building_phase_v0.md`](docs/build-reference/building_phase_v0.md)

---

## License

MIT — see [LICENSE](LICENSE).
