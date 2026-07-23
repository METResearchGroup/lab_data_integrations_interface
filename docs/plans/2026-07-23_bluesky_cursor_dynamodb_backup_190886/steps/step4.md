# Step 4: Document operational recovery and retention

## Goal

Add an operator runbook for inspecting backup freshness, restoring the disk cursor from DynamoDB after HPC loss, retention/overwrite behavior, and confirming resume. Link from the plan package.

## Files to inspect

- [`steps/step1.md`](step1.md) recovery rules
- [`data_platform/ingestion/jetstream_cursor.py`](../../../../data_platform/ingestion/jetstream_cursor.py)
- [`data_platform/ingestion/backup_jetstream_cursor.py`](../../../../data_platform/ingestion/backup_jetstream_cursor.py)
- [`docs/ops/cron/backup_jetstream_cursor.cron.example`](../../../../docs/ops/cron/backup_jetstream_cursor.cron.example)
- Existing runbook tone: [`docs/runbooks/HOW_TO_ADD_NEW_BATCH_DATA_JOB.md`](../../../../docs/runbooks/HOW_TO_ADD_NEW_BATCH_DATA_JOB.md)

## Files allowed to change

- [`docs/runbooks/HOW_TO_RECOVER_JETSTREAM_CURSOR_FROM_DYNAMODB.md`](../../../../docs/runbooks/HOW_TO_RECOVER_JETSTREAM_CURSOR_FROM_DYNAMODB.md) — **new**
- [`docs/plans/2026-07-23_bluesky_cursor_dynamodb_backup_190886/plan.md`](../plan.md) — link runbook under “What done looks like” / overview if missing
- Optional one-line link from a Bluesky backfill design doc **only if** one already exists and is the natural home; do not invent a large design doc rewrite

## Files forbidden to change

- Hot-path ingestion modules
- Live AWS resources

## Runbook contents (required sections)

1. **Purpose** — DynamoDB is DR mirror; disk remains primary for hot path.
2. **Prerequisites** — table name constant, backup key, AWS CLI profile/role (placeholders), example disk path.
3. **Inspect freshness** — example `aws dynamodb get-item` (documented, not executed in CI); fields `backed_up_at`, `disk_updated_at`, `content_sha256`.
4. **Restore procedure** — get item → verify checksum → write disk JSON via documented fields / helper CLI if exposed → confirm file validates.
5. **Overwrite / retention** — single latest key; successful daily job overwrites; failed job leaves prior intact.
6. **Confirm resume** — ingestion reads restored disk cursor; no DynamoDB on hot path.
7. **Example PR caveat** — this repo change ships code + tests + docs; table must be provisioned and cron installed separately before production use.

## What must pass / fail

**Pass**

- Runbook path exists and matches recovery rules in Step 1.
- Plan package links to the runbook.
- No secrets in the runbook.

**Fail**

- Instructing operators to write DynamoDB from the ingestion hot path.
- Undocumented “just pick a cursor” recovery without validation.
