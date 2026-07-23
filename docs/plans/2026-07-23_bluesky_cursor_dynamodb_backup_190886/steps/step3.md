# Step 3: Schedule example and observable failures

## Goal

Document (example only) how to run the backup daily on HPC via cron, and ensure failed runs are observable via logs + non-zero exit. Do **not** require deploying to HPC or live AWS credentials.

## Files to inspect

- [`data_platform/ingestion/backup_jetstream_cursor.py`](../../../../data_platform/ingestion/backup_jetstream_cursor.py) (CLI exit codes + log markers from Step 2)
- [`steps/step1.md`](step1.md) / [`steps/step2.md`](step2.md)

## Files allowed to change

- [`docs/ops/cron/backup_jetstream_cursor.cron.example`](../../../../docs/ops/cron/backup_jetstream_cursor.cron.example) — **new** example crontab snippet
- Optionally a thin shell wrapper under [`scripts/backup_jetstream_cursor.sh.example`](../../../../scripts/backup_jetstream_cursor.sh.example) if helpful
- Plan step docs only as needed for accuracy

## Files forbidden to change

- Production cron on any host
- AWS IAM / account config in-repo secrets
- Hot-path ingestion modules

## Deliverables

1. **Example cron** (daily, e.g. `15 6 * * *`) that:
   - `cd`s to repo root
   - sets `PYTHONPATH=.`
   - invokes `uv run python data_platform/ingestion/backup_jetstream_cursor.py --cursor-path ...`
   - redirects stdout/stderr to a log file path placeholder
2. **Observability contract** (documented in example comments + runbook Step 4):
   - Success log substring: `jetstream_cursor_backup_succeeded`
   - Failure log substring: `jetstream_cursor_backup_failed`
   - Process exit code `0` success / non-zero failure (cron mail / monitoring can key off this)
3. Env placeholders only: `AWS_REGION`, `AWS_PROFILE` or instance role note, `JETSTREAM_CURSOR_PATH` — no real secrets committed

## What must pass / fail

**Pass**

- Example file exists and references the real CLI module path.
- Comments state this is **example / not deployed** by this PR.
- `rg -n "jetstream_cursor_backup_(succeeded|failed)" data_platform/ingestion/backup_jetstream_cursor.py` finds both markers.

**Fail**

- Committing real hostnames, keys, or `.env` values.
- Requiring live DynamoDB for the example to be considered complete.
