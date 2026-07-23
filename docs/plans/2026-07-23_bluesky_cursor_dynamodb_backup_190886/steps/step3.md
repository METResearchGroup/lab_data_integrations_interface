# Step 3: Document HPC schedule and failure observability

## Objective

Provide an example daily schedule and make backup failures observable via exit code and log markers. Do not deploy to a real HPC host in this example PR.

## Allowed to change

- `docs/runbooks/HOW_TO_BACKUP_BLUESKY_JETSTREAM_CURSOR.md`
- `docs/ops/cron/backup_jetstream_cursor.cron.example`
- `docs/plans/2026-07-23_bluesky_cursor_dynamodb_backup_190886/examples/crontab.example`
- `data_platform/ingestion/backup_jetstream_cursor.py` — `SUCCESS_MARKER` / `FAILURE_MARKER`

## Forbidden

- Committing AWS keys or host secrets
- Changing ingestion hot-path modules

## Pass / fail

```bash
test -f docs/ops/cron/backup_jetstream_cursor.cron.example
test -f docs/plans/2026-07-23_bluesky_cursor_dynamodb_backup_190886/examples/crontab.example
rg 'jetstream_cursor_backup_(succeeded|failed)' data_platform/ingestion/backup_jetstream_cursor.py docs/runbooks/HOW_TO_BACKUP_BLUESKY_JETSTREAM_CURSOR.md
```

Expected: example crontab exists; both markers documented and present in code.

## Done when

Operators can wire cron from the example and alert on exit code / failure marker without reading DynamoDB.
