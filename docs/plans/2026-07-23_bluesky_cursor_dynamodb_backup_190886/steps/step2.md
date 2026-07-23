# Step 2: Implement daily backup job with safe writes and tests

## Objective

Implement disk cursor load/validate, DynamoDB backup write, offline restore-from-item-file, and Typer CLI. Cover success and non-corrupting failure modes with mocked DynamoDB (no live AWS).

## Inspect

- `data_platform/ingestion/jetstream_cursor.py`
- `data_platform/aws/dynamodb.py`
- `tests/data_platform/aws/test_dynamodb.py`

## Allowed to change

- `data_platform/ingestion/jetstream_cursor.py`
- `data_platform/ingestion/backup_jetstream_cursor.py`
- `data_platform/aws/dynamodb.py` — `get_item` helper (optional for future live restore)
- `tests/data_platform/ingestion/test_jetstream_cursor.py`
- `tests/data_platform/ingestion/test_backup_jetstream_cursor.py`
- `tests/data_platform/aws/test_dynamodb.py`

## Forbidden

- Sync scripts (`sync_bluesky.py`, etc.)
- Live AWS calls required to run tests

## Pass / fail

```bash
uv run pytest tests/data_platform/ingestion/test_jetstream_cursor.py tests/data_platform/ingestion/test_backup_jetstream_cursor.py tests/data_platform/aws/test_dynamodb.py -q
```

Expected: all pass.

```bash
rg 'DynamoDB|put_item|CURSOR_BACKUP' data_platform/ingestion/sync_bluesky.py
```

Expected: no matches.

## Done when

`run_backup` validates before `put_item`; DynamoDB failures do not issue a second/partial write; CLI exit codes are covered.
