# Remote company scripts repo

Keep company-specific jobs out of Alfred core. Put curated script packages (or an arsenal-style `py/` package) in a Git repo; Alfred pulls them with the same **git token** in Secrets.

Operator overview (config, invoke, logs): [README — Company scripts](../../README.md#company-scripts) and [README — Logs](../../README.md#logs).

## Alfred config (`.alfred/config.yaml`)

```yaml
git:
  enabled: true
  provider: github
  token: ""          # set in Admin → Secrets

scripts:
  enabled: true
  timeout_seconds: 300    # max 1800 — raise for Athena oneshots
  remote:
    repo: YourOrg/your-scripts   # e.g. FlexyPe/alfred_scripts or FlexyPe/arsenal
    branch: main
    path: scripts                # folder of script.yaml packages (use a real dir)
    playbooks_path: playbooks    # optional — sync into .alfred/playbooks/
    requirements_file: ""        # or py/requirements.txt
    python_mode: isolated        # isolated | alfred
    sync_on_startup: true
    sync_on_git_sync: true
```

For a monorepo like **FlexyPe/arsenal**, set `path` to a small directory that contains packages (or wrappers), not the entire `py/` tree — otherwise Alfred indexes every folder as a legacy script. Point `requirements_file` at `py/requirements.txt` and run `alfred scripts setup` so Alfred does `pip install -e ./py` into `.alfred/scripts-venv`.

## Commands

```bash
# Pull repo + refresh catalog (installs deps only if the venv is new / stamp changed)
alfred scripts sync

# Install / refresh deps (no git pull). Same idea as arsenal `make setup-py`:
# venv + pip + `pip install -e ./py` when pyproject.toml exists.
alfred scripts setup
alfred scripts setup --pull

# Also runs scripts sync when scripts.remote.sync_on_git_sync is true
alfred git sync
```

Admin UI → **Scripts**: **Sync** (`POST /api/scripts/sync`) and **Install deps** (`POST /api/scripts/setup`).

## Recommended repo layout

```
YourOrg/your-scripts/
├── README.md
├── requirements.txt          # deps for isolated python_mode
├── scripts/
│   ├── tech_support/
│   │   ├── script.yaml
│   │   ├── main.py
│   │   └── lib/
│   ├── daily_athena_report/
│   │   ├── script.yaml
│   │   └── main.py
│   └── merchant_lookup/
│       ├── script.yaml
│       └── main.py
└── playbooks/                # optional
    └── tech-support-tickets.md
```

Arsenal-style (editable package):

```
YourOrg/arsenal/
├── py/
│   ├── pyproject.toml
│   ├── requirements.txt
│   └── jobs/
│       └── daily_metrics_oneshot.py
└── output/                   # scripts.remote.path — not the whole py/ tree
```

Local wrappers under `.alfred/scripts/{name}/` can call into the mirrored repo and override a remote package with the same name.

### `script.yaml` example

```yaml
name: tech_support/list_unresolved
description: List Slack workflow tickets without white_check_mark in #tech-support
entry: main.py
runtime: python3
triggers:
  - list unresolved tickets
args:
  - name: since_days
    description: Look back N days
    default: "30"
```

Scripts receive args as JSON argv + `ALFRED_SCRIPT_ARGS` env var.

## Python dependencies

| `python_mode` | When to use |
|---------------|-------------|
| **`isolated`** (default) | Own `requirements.txt` and/or `py/pyproject.toml`. Alfred uses `.alfred/scripts-venv/`. |
| **`alfred`** | Only libraries already installed with Alfred (boto3, requests, …). No extra pip. |

**Install order (`alfred scripts setup`):**

1. Create `.alfred/scripts-venv` if missing
2. `pip install -U pip`
3. `pip install -e ./py` when `py/pyproject.toml` or repo-root `pyproject.toml` exists
4. `pip install -r` the resolved requirements file (if any)

**Requirements file search order:**

1. `scripts.remote.requirements_file` (if set)
2. `{scripts_root}/requirements.txt`
3. `{repo}/py/requirements.txt`
4. `{repo}/requirements.txt`

Startup sync **skips pip** when a deps stamp already matches. After you change requirements, run `alfred scripts setup` (or **Install deps**).

**PYTHONPATH:** Alfred adds the remote scripts root and each package directory so `from lib.foo import bar` works inside packages.

**Tips:**

- Pin versions in `requirements.txt` for reproducible runs.
- Prefer stdlib + Alfred deps when possible (`python_mode: alfred`).
- For heavy stacks (pandas, Athena), use `isolated` and keep requirements minimal.
- Local overrides: `.alfred/scripts/` — same name wins over remote.

## Invoking (chat / Slack / cron)

Listing a script in the LLM prompt is **not** enough. Bind a playbook:

- Chat: `run {playbook_or_script_name}` or a playbook **trigger** phrase
- Playbook: `type: plan_template`, `allowed_tools` includes `run_company_script`
- Cron: `schedule_management` enqueues `run {skill_name}`

If the reply is **LLM only** with no tool calls, the job did not run. See [README — Logs](../../README.md#logs).

## Scheduling

Create a cron job that calls a playbook linking your script:

```yaml
# .alfred/playbooks/nightly-report.md (or synced from repo)
---
name: nightly-report
mode: workflow
type: plan_template
triggers:
  - nightly report
scripts:
  - daily_athena_report
allowed_tools:
  - run_company_script
---
Run `daily_athena_report` with yesterday's date.
```

Then in Slack: `@alfred schedule nightly report every weekday at 9am IST`

Set `scripts.timeout_seconds` high enough for the job (Athena oneshots often need 10–30 minutes).

## Logs

| Path | Use |
|------|-----|
| `.alfred/alfred.log` | `Scripts repo sync: …`, routing, `run_company_script` |
| `.alfred/run/alfred.stdout.log` | `alfred up` / uvicorn (sync on startup) |
| Admin → Usage | Checkpoints for the task |
| Admin → Routing | Whether the playbook/tool plan bound |

```bash
tail -f .alfred/alfred.log
rg "Scripts repo sync|run_company_script|Named run skill|Plan template" .alfred/alfred.log
```

## Security

- Only connect private repos you trust — scripts run with Alfred's environment (AWS/JIRA tokens available to the process).
- Review script PRs like production code.
