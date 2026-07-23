# Step 2: Implement daily backup job with safe writes and tests

## Goal

Implement a standalone, testable backup job: read disk cursor → validate → build DynamoDB item → conditional-safe put → log success/failure. Prefer TDD. Mock boto3/DynamoDB; no real AWS.

## Scope (implement-from-spec)

- **Caller:** CLI / `main` in `data_platform/ingestion/backup_jetstream_cursor.py` calling `run_backup(cursor_path, dynamodb, table, backup_key, *, clock=...)`.
- **Happy-path slice:** load disk → validate → build item → `put_item` → log success → return `BackupResult(ok=True)`.
- **Out of scope:** HPC cron install, live credentials, changing sync_bluesky hot path.

## Files to inspect

- [`steps/step1.md`](step1.md) (frozen contracts)
- [`data_platform/aws/dynamodb.py`](../../../../data_platform/aws/dynamodb.py)
- [`tests/data_platform/aws/test_dynamodb.py`](../../../../tests/data_platform/aws/test_dynamodb.py)
- [`data_platform/orchestration/pipeline_run.py`](../../../../data_platform/orchestration/pipeline_run.py)
- [`data_platform/curate/curate_bluesky.py`](../../../../data_platform/curate/curate_bluesky.py) (Typer CLI pattern)

## Files allowed to change

- [`data_platform/aws/constants.py`](../../../../data_platform/aws/constants.py) — add `CURSOR_BACKUP_TABLE`
- [`data_platform/aws/dynamodb.py`](../../../../data_platform/aws/dynamodb.py) — optional thin `put_item` wrapper only if needed; prefer injecting a small port
- [`data_platform/ingestion/jetstream_cursor.py`](../../../../data_platform/ingestion/jetstream_cursor.py) — **new**: disk read/validate/write helpers + checksum
- [`data_platform/ingestion/backup_jetstream_cursor.py`](../../../../data_platform/ingestion/backup_jetstream_cursor.py) — **new**: backup job + Typer CLI
- [`tests/data_platform/ingestion/test_jetstream_cursor.py`](../../../../tests/data_platform/ingestion/test_jetstream_cursor.py) — **new**
- [`tests/data_platform/ingestion/test_backup_jetstream_cursor.py`](../../../../tests/data_platform/ingestion/test_backup_jetstream_cursor.py) — **new**
- [`tests/data_platform/aws/test_dynamodb.py`](../../../../tests/data_platform/aws/test_dynamodb.py) — only if DynamoDB helper API extended

## Files forbidden to change

- [`data_platform/ingestion/sync_bluesky.py`](../../../../data_platform/ingestion/sync_bluesky.py)
- [`data_platform/ingestion/sync_checkpoint.py`](../../../../data_platform/ingestion/sync_checkpoint.py)
- [`data_platform/ingestion/sync_twitter.py`](../../../../data_platform/ingestion/sync_twitter.py)
- [`data_platform/ingestion/sync_reddit.py`](../../../../data_platform/ingestion/sync_reddit.py)
- Any `.env` / secret files

## Implementation units (dependency order)

1. `JetstreamDiskCursor` model + `compute_content_sha256` + `read_disk_cursor` / `write_disk_cursor` / `validate` errors
2. `build_backup_item(...)` from disk cursor + metadata
3. `run_backup(...)` orchestration with injectable DynamoDB-like `put_item`
4. Typer CLI: `--cursor-path`, optional `--table` / `--backup-key`, exit codes
5. Optional `restore_disk_cursor_from_backup_item(item, path)` for runbook/tests (no live get_item required in unit tests)

## Test design (given / when / then)

1. **Happy path**
   - given valid disk cursor file
   - when `run_backup`
   - then DynamoDB `put_item` called once with correct item fields + matching `content_sha256`
   - and result ok; success log marker present

2. **Missing disk cursor**
   - given path does not exist
   - when `run_backup`
   - then no `put_item`; result not ok; failure log marker; non-zero CLI exit

3. **Corrupt disk cursor**
   - given invalid JSON or bad `format_version` / negative cursor
   - when `run_backup`
   - then no `put_item`; failure observable

4. **DynamoDB write failure does not corrupt**
   - given valid disk; mock `put_item` raises
   - when `run_backup`
   - then exception surfaced / result not ok
   - and no prior `delete_item`; only the failed `put_item` attempted (prior backup untouched)

5. **Restore helper**
   - given valid backup item dict
   - when `restore_disk_cursor_from_backup_item`
   - then disk file matches schema v1 and cursor/updated_at from item
   - given checksum mismatch → raise; disk unchanged

## What must pass / fail

**Pass**

```bash
uv run pytest tests/data_platform/ingestion/test_jetstream_cursor.py tests/data_platform/ingestion/test_backup_jetstream_cursor.py tests/data_platform/aws/test_dynamodb.py -q
```

Expected: all new/changed tests green; no network/AWS.

**Fail**

- Tests that require AWS credentials or real tables
- Any DynamoDB import/write added to hot-path sync modules
- Backup writing before disk validation succeeds
