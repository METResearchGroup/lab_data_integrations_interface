# How to Backup and Recover the Bluesky Jetstream Cursor

Disaster-recovery (DR) backup for the Jetstream ingestion cursor. The **hot path stays on HPC disk**; DynamoDB holds a daily off-path copy so an HPC outage does not erase the only resume checkpoint.

This example PR implements the job and documents operations. It does **not** provision the DynamoDB table or install cron on a live HPC host.

Related: [Issue #122](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/122), plan `docs/plans/2026-07-23_bluesky_cursor_dynamodb_backup_190886/`.

---

## Disk vs DynamoDB roles

| Store | Role | Cadence |
| ----- | ---- | ------- |
| HPC disk `cursor.json` | Source of truth for live resume | Frequent (ingestion checkpoints) |
| DynamoDB table `lab-data-integrations-interface-cursor-backups` | Single-row DR mirror (`backup_key=bluesky_jetstream_cursor_latest`) | Daily scheduled job |

overwrite/retention: **one logical latest row**. A successful backup replaces the prior item in full via `put_item`. A failed backup never deletes first and never writes a partial item; the previous good row remains.

Disk JSON contract (`format_version=1`):

- `format_version` (int, must be `1`)
- `cursor` (non-negative int, Jetstream Unix microseconds)
- `updated_at` (timezone-aware ISO-8601)

Backup item also includes `schema_version`, `backed_up_at`, `disk_updated_at`, `source_path`, and `content_sha256` for freshness/validation.

---

## Schedule (example)

See [`docs/ops/cron/backup_jetstream_cursor.cron.example`](../ops/cron/backup_jetstream_cursor.cron.example)
(plan package also keeps a short copy under
[`examples/crontab.example`](../plans/2026-07-23_bluesky_cursor_dynamodb_backup_190886/examples/crontab.example)).

```bash
cd /path/to/lab_data_integrations_interface
export JETSTREAM_CURSOR_PATH=/path/to/cursor.json
PYTHONPATH=. uv run python data_platform/ingestion/backup_jetstream_cursor.py backup \
  --cursor-path "$JETSTREAM_CURSOR_PATH"
```

### Observability

- Success: process exit code `0` and log line containing `jetstream_cursor_backup_succeeded`
- Failure: process exit code `1` and log line containing `jetstream_cursor_backup_failed`
- Alert on non-zero cron exit or on the failure log phrase. Do not infer health solely by reading DynamoDB.

---

## Inspect / offline restore (no live AWS required)

Export a backup item JSON from DynamoDB (ops console / `get_item`) when available, then restore offline:

```bash
PYTHONPATH=. uv run python data_platform/ingestion/backup_jetstream_cursor.py \
  restore-from-item-file \
  --item-path /path/to/backup_item.json \
  --cursor-path "$JETSTREAM_CURSOR_PATH"
```

Validate the restored disk file:

```bash
PYTHONPATH=. python -c "from pathlib import Path; from data_platform.ingestion.jetstream_cursor import read_disk_cursor; print(read_disk_cursor(Path('$JETSTREAM_CURSOR_PATH')))"
```

---

## Recover after HPC loss

1. Prefer a local disk cursor if it still exists and validates (`read_disk_cursor`).
2. If disk is missing or corrupt, obtain the latest DynamoDB item for `backup_key=bluesky_jetstream_cursor_latest` and write it to a JSON file.
3. Judge freshness with `backed_up_at` / `disk_updated_at`. Prefer backups newer than ~48 hours; older backups are a last resort after operator review (Jetstream replay window is limited).
4. Run `restore-from-item-file` to rewrite the disk cursor.
5. Restart Jetstream ingestion so it resumes from the restored disk `cursor`. DynamoDB is not updated by restore.

---

## What this does not do

- Does not write DynamoDB on every cursor advance during ingestion.
- Does not create the DynamoDB table (ops / IaC outside this example).
- Does not install the crontab on HPC (example file only).
