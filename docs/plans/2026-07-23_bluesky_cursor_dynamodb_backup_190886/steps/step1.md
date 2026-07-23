# Step 1: Freeze backup and recovery contracts

## Objective

Lock the on-disk Jetstream cursor format, the DynamoDB backup item shape, overwrite semantics, and recovery selection rules so Steps 2–4 implement against a fixed contract. This step is documentation + constants only (no backup behavior yet).

## Inspect

- `docs/plans/2026-07-23_bluesky_cursor_dynamodb_backup_190886/plan.md`
- `docs/design_docs/2026-07-13_bluesky_backfill_app.md` (on PR `backfill_design_doc` if absent locally)
- `data_platform/aws/constants.py`
- `data_platform/aws/dynamodb.py`
- `data_platform/orchestration/pipeline_run.py` (existing DynamoDB item pattern)

## Allowed to change

- `docs/plans/2026-07-23_bluesky_cursor_dynamodb_backup_190886/plan.md` (contract table only if needed)
- `docs/plans/2026-07-23_bluesky_cursor_dynamodb_backup_190886/steps/step1.md` (this file)
- `data_platform/aws/constants.py` — add table name constant only
- **New** `data_platform/ingestion/jetstream_cursor.py` — dataclasses + format_version constants + path helpers; stub read/write raising `NotImplementedError` is OK until Step 2

## Forbidden

- `data_platform/ingestion/sync_bluesky.py` and all other sync scripts
- Real AWS table creation / Terraform / console changes
- Any DynamoDB write from an ingestion hot path

## Contracts (frozen)

### Disk cursor file

- Default relative path (example / HPC): `$JETSTREAM_CURSOR_PATH` or default `data_platform/data/bluesky/jetstream/jetstream_cursor.json`
- JSON object, UTF-8, atomic replace on write (write temp + rename) when writer is implemented
- Required fields:

| Field | Type | Rules |
| ----- | ---- | ----- |
| `cursor_us` | int | Jetstream Unix microseconds; must be `> 0` |
| `format_version` | int | Must equal `CURSOR_FORMAT_VERSION` (1) |
| `updated_at` | str | ISO-8601 UTC timestamp of last successful disk checkpoint |
| `source` | str | Must be `"jetstream"` |

### DynamoDB backup item (single latest row)

- Table constant: `JETSTREAM_CURSOR_BACKUP_TABLE = "lab-data-integrations-interface-jetstream-cursor-backup"`
- Partition key: `backup_id` (string). Canonical value: `"bluesky_jetstream_cursor"`
- Overwrite policy: **one row**; successful backup replaces the previous item in full via `put_item`
- Failure policy: never call `put_item` with a partial/invalid item; a failed `put_item` leaves the prior item unchanged

| Field | Type | Notes |
| ----- | ---- | ----- |
| `backup_id` | str | PK; always `bluesky_jetstream_cursor` |
| `cursor_us` | number | Copied from disk |
| `format_version` | number | Copied from disk |
| `disk_updated_at` | str | Disk `updated_at` |
| `backed_up_at` | str | ISO-8601 UTC when backup job succeeded |
| `source_path` | str | Absolute path of disk file read |
| `status` | str | Always `"valid"` for written items |

### Recovery selection

1. Prefer HPC disk cursor when present and valid.
2. If disk missing/corrupt, load DynamoDB backup where `status == "valid"` and `format_version == CURSOR_FORMAT_VERSION`.
3. Reject backup if `backed_up_at` is older than 48 hours unless operator passes an explicit `--force-stale` flag (documented in runbook).
4. Restore writes a new valid disk cursor file; does not mutate DynamoDB.

## Pass / fail

```bash
rg 'JETSTREAM_CURSOR_BACKUP_TABLE' data_platform/aws/constants.py
```

Expected: one match with the table name above.

```bash
python -c "from data_platform.ingestion.jetstream_cursor import CURSOR_FORMAT_VERSION, BACKUP_ID; assert CURSOR_FORMAT_VERSION == 1; assert BACKUP_ID == 'bluesky_jetstream_cursor'"
```

Expected: exit 0 (after Step 1 scaffolding lands).

## Done when

Contracts above are written here and mirrored by constants/types in `jetstream_cursor.py`; no backup CLI behavior required yet.
