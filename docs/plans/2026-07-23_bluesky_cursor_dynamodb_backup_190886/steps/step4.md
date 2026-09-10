# Step 4: Document recovery and retention

## Objective

Document how to inspect backup freshness, restore after HPC loss, overwrite/retention behavior, and how to confirm resume.

## Allowed to change

- `docs/runbooks/HOW_TO_BACKUP_BLUESKY_JETSTREAM_CURSOR.md`
- `docs/plans/2026-07-23_bluesky_cursor_dynamodb_backup_190886/plan.md` (runbook link)

## Forbidden

- Live restore against production DynamoDB in CI

## Pass / fail

```bash
rg 'overwrite|restore-from-item-file|48|content_sha256' docs/runbooks/HOW_TO_BACKUP_BLUESKY_JETSTREAM_CURSOR.md
uv run pytest tests/data_platform/ingestion/test_jetstream_cursor.py tests/data_platform/ingestion/test_backup_jetstream_cursor.py tests/data_platform/aws/test_dynamodb.py -q
```

Expected: runbook covers retention/restore/freshness; tests still green.

## Done when

Operators can recover from the runbook alone; Issue #122 documentation acceptance criterion is met for this example PR.
