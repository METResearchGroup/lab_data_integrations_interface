"""Daily DynamoDB disaster-recovery backup for the Bluesky Jetstream disk cursor.

Example / offline-capable entrypoint: reads the on-disk cursor contract, builds a
metadata-rich DynamoDB item, and writes it only after validation. Failed writes
do not delete or mutate a prior good backup (atomic put_item only).

Does not run on the ingestion hot path. Live AWS table provisioning and HPC cron
install are out of scope for the example PR — see the recovery runbook and cron
example under docs/.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/ingestion/backup_jetstream_cursor.py \\
        backup --cursor-path data_platform/data/bluesky/jetstream/cursor.json
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import typer

from data_platform.aws.constants import CURSOR_BACKUP_TABLE, JETSTREAM_CURSOR_BACKUP_KEY
from data_platform.aws.dynamodb import DynamoDB
from data_platform.ingestion.jetstream_cursor import (
    JetstreamCursorError,
    build_backup_item,
    read_disk_cursor,
    restore_disk_cursor_from_backup_item,
)

logger = logging.getLogger(__name__)

SUCCESS_MARKER = "jetstream_cursor_backup_succeeded"
FAILURE_MARKER = "jetstream_cursor_backup_failed"

app = typer.Typer(add_completion=False)


class DynamoDBPutPort(Protocol):
    def put_item(self, table: str, item: dict) -> None: ...


@dataclass(frozen=True, slots=True)
class BackupResult:
    ok: bool
    message: str
    item: dict | None = None


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def run_backup(
    cursor_path: Path,
    dynamodb: DynamoDBPutPort,
    *,
    table: str = CURSOR_BACKUP_TABLE,
    backup_key: str = JETSTREAM_CURSOR_BACKUP_KEY,
    clock: Callable[[], str] = _utc_now_iso,
) -> BackupResult:
    """Read/validate disk cursor and put a full backup item. Never delete first."""
    try:
        disk = read_disk_cursor(cursor_path)
        item = build_backup_item(
            disk,
            backup_key=backup_key,
            source_path=str(cursor_path.resolve()),
            backed_up_at=clock(),
        )
        dynamodb.put_item(table, item)
    except JetstreamCursorError as exc:
        logger.error("%s: %s", FAILURE_MARKER, exc)
        return BackupResult(ok=False, message=str(exc))
    except Exception as exc:
        logger.error("%s: dynamodb write failed: %s", FAILURE_MARKER, exc)
        return BackupResult(ok=False, message=f"dynamodb write failed: {exc}")

    logger.info(
        "%s: backup_key=%s cursor=%s backed_up_at=%s",
        SUCCESS_MARKER,
        item["backup_key"],
        item["cursor"],
        item["backed_up_at"],
    )
    return BackupResult(ok=True, message="ok", item=item)


@app.command("backup")
def backup_cmd(
    cursor_path: Path = typer.Option(
        ...,
        "--cursor-path",
        envvar="JETSTREAM_CURSOR_PATH",
        help="Path to Jetstream disk cursor JSON",
    ),
    table: str = typer.Option(CURSOR_BACKUP_TABLE, "--table"),
    backup_key: str = typer.Option(JETSTREAM_CURSOR_BACKUP_KEY, "--backup-key"),
) -> None:
    """Copy the latest valid disk cursor into DynamoDB (DR mirror)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = run_backup(cursor_path, DynamoDB(), table=table, backup_key=backup_key)
    if not result.ok:
        raise typer.Exit(code=1)


@app.command("restore-from-item-file")
def restore_from_item_file_cmd(
    item_path: Path = typer.Option(..., "--item-path", help="JSON file of a DynamoDB backup item"),
    cursor_path: Path = typer.Option(
        ...,
        "--cursor-path",
        envvar="JETSTREAM_CURSOR_PATH",
        help="Destination disk cursor path",
    ),
) -> None:
    """Restore disk cursor from a saved backup item JSON (no live AWS required)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        item = json.loads(item_path.read_text(encoding="utf-8"))
        disk = restore_disk_cursor_from_backup_item(item, cursor_path)
    except (OSError, UnicodeError, json.JSONDecodeError, JetstreamCursorError) as exc:
        logger.error("%s: restore failed: %s", FAILURE_MARKER, exc)
        raise typer.Exit(code=1) from exc
    logger.info("jetstream_cursor_restore_succeeded: cursor=%s path=%s", disk.cursor, cursor_path)


if __name__ == "__main__":
    app()
