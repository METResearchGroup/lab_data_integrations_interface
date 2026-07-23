# Step 1: Freeze backup and recovery contracts

## Objective

Lock the on-disk Jetstream cursor format, the DynamoDB backup item shape, overwrite semantics, and recovery selection rules so Steps 2–4 implement against a fixed contract.

## Inspect

- `docs/plans/2026-07-23_bluesky_cursor_dynamodb_backup_190886/plan.md`
- `data_platform/aws/constants.py`
- `data_platform/aws/dynamodb.py`
- `data_platform/orchestration/pipeline_run.py`

## Allowed to change

- `data_platform/aws/constants.py` — `CURSOR_BACKUP_TABLE`, `JETSTREAM_CURSOR_BACKUP_KEY`
- `data_platform/ingestion/jetstream_cursor.py` — disk + backup item contracts

## Forbidden

- `data_platform/ingestion/sync_bluesky.py` and other sync scripts
- Real AWS table creation
- DynamoDB writes from the ingestion hot path

## Contracts (frozen)

### Disk cursor file

- Example path: `$JETSTREAM_CURSOR_PATH` or `data_platform/data/bluesky/jetstream/cursor.json`
- JSON object, UTF-8, atomic write (`tmp` + `os.replace`)

| Field | Type | Rules |
| ----- | ---- | ----- |
| `format_version` | int | Must equal `DISK_FORMAT_VERSION` (`1`) |
| `cursor` | int | Non-negative Jetstream Unix microseconds |
| `updated_at` | str | Timezone-aware ISO-8601 |

### DynamoDB backup item (single latest row)

- Table: `CURSOR_BACKUP_TABLE = "lab-data-integrations-interface-cursor-backups"`
- Partition key field: `backup_key` — canonical value `JETSTREAM_CURSOR_BACKUP_KEY = "bluesky_jetstream_cursor_latest"`
- Overwrite: successful `put_item` replaces the prior item in full
- Failure: never delete-then-put; never `put_item` with an unvalidated/partial item

| Field | Type | Notes |
| ----- | ---- | ----- |
| `backup_key` | str | PK |
| `cursor` | number/int | From disk |
| `format_version` | number/int | From disk |
| `schema_version` | number/int | `BACKUP_SCHEMA_VERSION` (`1`) |
| `disk_updated_at` | str | Disk `updated_at` |
| `backed_up_at` | str | When backup job succeeded |
| `source_path` | str | Absolute path read |
| `content_sha256` | str | Hash of `format_version:cursor:disk_updated_at` |

### Recovery selection

1. Prefer valid HPC disk cursor.
2. Else restore from DynamoDB backup item (or exported JSON via `restore-from-item-file`).
3. Prefer backups with `backed_up_at` within ~48h; older only after operator review.
4. Restore writes disk only; does not mutate DynamoDB.

## Pass / fail

```bash
rg 'CURSOR_BACKUP_TABLE|JETSTREAM_CURSOR_BACKUP_KEY' data_platform/aws/constants.py
```

Expected: both constants present.

```bash
PYTHONPATH=. uv run python -c "from data_platform.ingestion.jetstream_cursor import DISK_FORMAT_VERSION, BACKUP_SCHEMA_VERSION; assert DISK_FORMAT_VERSION == 1 and BACKUP_SCHEMA_VERSION == 1"
```

Expected: exit 0.

## Done when

Contracts above match `jetstream_cursor.py` and constants.
