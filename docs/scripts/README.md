# Company scripts (examples)

Copy packages from `examples/` into **`.alfred/scripts/`** on your Alfred host.  
Scripts are **local-only** (inside `.alfred/`, gitignored) — same model as domain playbooks.

## Layout

Each script is a **folder package** with a manifest and one entry point. Helper files can live alongside it.

```
.alfred/
  scripts/
    daily_error_summary/
      script.yaml          # name, entry, runtime, args
      main.py              # entry point
      lib/
        formatting.py      # optional helpers
    checkout/daily_report/
      script.yaml
      main.sh
  playbooks/
    checkout_events.md     # references scripts: [checkout/daily_report]
```

Legacy flat scripts (`report.py` + optional `report.yaml` at the scripts root) still work, but packages are preferred for multi-file modules.

## Manifest (`script.yaml`)

```yaml
name: checkout/daily_report
description: Roll up checkout errors for a date partition
entry: main.py
runtime: python3   # python3 | bash | sh | node | deno | go | custom
args:
  - name: date
    description: Partition date YYYY-MM-DD
    required: true
  - name: environment
    default: production
```

For `runtime: custom`, add a `command` list with `{entry}`, `{args_json}`, and `{package_dir}` placeholders.

## Playbook link

In a domain playbook frontmatter:

```yaml
---
name: checkout_events
mode: investigation
triggers:
  - checkout errors
allowed_tools:
  - run_company_script
  - athena_query
scripts:
  - checkout/daily_report
  - daily_error_summary
---
```

When this playbook matches, Alfred injects the script catalog into the prompt and can call  
`run_company_script` with structured args instead of improvising SQL.

Script names use nested paths (`checkout/daily_report`). The alias `checkout__daily_report` also works.

## Script contract

- Entry is invoked by Alfred with JSON args as argv[1] and in env `ALFRED_SCRIPT_ARGS`
- Env also includes `ALFRED_SCRIPT_NAME`, `ALFRED_SCRIPT_ENTRY`, and working directory set to the package folder
- Print human-readable stdout for Slack; optional JSON object on the last line for structured tables
- Keep secrets out of scripts — read from env or Alfred config on the host

## Admin UI

Configure → **Scripts** lists packages, edits files, and creates new nested packages. Alfred can also  
create and update packages via **`create_company_script_package`** and **`write_company_script_file`**  
during Slack/chat workflows (e.g. while setting up a schedule); use the admin UI to review or refine them.

## Schedules

Scheduled jobs (`create_schedule`) generate workflow playbooks with `run_company_script` in  
`allowed_tools`. Reference script names in the schedule instructions for repeatable cron work.

See `examples/daily_error_summary/` for a starter package.
