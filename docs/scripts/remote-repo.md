# Remote company scripts repo (`FlexyPe/alfred_scripts`)

Keep FlexyPe-specific logic out of Alfred core. Put curated script packages in a Git repo; Alfred pulls them using the same **git token** in Secrets.

## Alfred config (`.alfred/config.yaml`)

```yaml
git:
  enabled: true
  provider: github
  token: ""          # set in Admin → Secrets

scripts:
  enabled: true
  timeout_seconds: 300
  remote:
    repo: FlexyPe/alfred_scripts
    branch: main
    path: scripts                    # folder inside the repo
    playbooks_path: playbooks          # optional — sync into .alfred/playbooks/
    requirements_file: requirements.txt
    python_mode: isolated              # isolated | alfred
    sync_on_startup: true
    sync_on_git_sync: true
```

## Commands

```bash
# Pull repo + pip install requirements into .alfred/scripts-venv/
alfred scripts sync

# Also runs scripts sync when scripts.remote.sync_on_git_sync is true
alfred git sync
```

Admin UI: **POST `/api/scripts/sync`**

## Recommended repo layout

```
FlexyPe/alfred_scripts/
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

### `script.yaml` example

```yaml
name: tech_support/list_unresolved
description: List Slack workflow tickets without white_check_mark in #tech-support
entry: main.py
runtime: python3
args:
  - name: since_days
    description: Look back N days
    default: "30"
```

Scripts receive args as JSON argv + `ALFRED_SCRIPT_ARGS` env var.

## Python dependencies (avoid import failures)

| `python_mode` | When to use |
|---------------|-------------|
| **`isolated`** (default) | Script repo has its own `requirements.txt`. Alfred creates `.alfred/scripts-venv/` and runs scripts with that Python after `alfred scripts sync`. |
| **`alfred`** | Scripts only use libraries already installed with Alfred (boto3, requests, etc.). No extra pip install — fastest, but limited to Alfred's deps. |

**Requirements file search order:**

1. `scripts.remote.requirements_file` (if set)
2. `{repo}/scripts/requirements.txt`
3. `{repo}/requirements.txt`

**PYTHONPATH:** Alfred adds the remote scripts root and each package directory so `from lib.foo import bar` works inside packages.

**Tips:**

- Pin versions in `requirements.txt` for reproducible runs.
- Prefer stdlib + Alfred deps when possible (`python_mode: alfred`).
- For heavy stacks (pandas, polars), use `isolated` and keep requirements minimal.
- Local overrides: put hotfix packages under `.alfred/scripts/` — same name overrides the remote package.

## Scheduling

Create a cron job that calls a playbook linking your script:

```yaml
# .alfred/playbooks/nightly-report.md (or synced from repo)
---
name: nightly-report
triggers:
  - nightly report
scripts:
  - daily_athena_report
---
Run `daily_athena_report` with yesterday's date.
```

Then in Slack: `@alfred schedule nightly report every weekday at 9am IST`

## Security

- Only connect private repos you trust — scripts run with Alfred's environment (AWS/JIRA tokens available to the process).
- Review script PRs like production code.
