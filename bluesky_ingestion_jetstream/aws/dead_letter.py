"""Durable landing place for batches whose Iceberg commit could not be made.

These rows are not in the tables. Every query run afterwards is short by exactly
this batch, and nothing about the table itself will say so -- the log line and
the presence of files under this prefix are the only signals, which is why both
matter more than they look.

Two decisions worth keeping:

The path sits above `bluesky/`, well outside the warehouse root. A dead-letter
file is unreferenced by any Iceberg table by definition, and unreferenced files
under a table's location are precisely what orphan cleanup deletes. Storing them
in the warehouse means a future maintenance sweep silently destroys the only
remaining copy of unrecovered data.

The Parquet is built from the *module* schema, not the table's. That is what
keeps this path working in the case it is most needed: if the declared schema and
the table's have diverged, the append fails on incompatibility while this write
still succeeds, because the rows came from parsers that produce exactly this
shape.
"""

import logging
from datetime import UTC, datetime
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq
from pyarrow.fs import FileSystem, S3FileSystem

from bluesky_ingestion_jetstream.aws.constants import (
    AWS_REGION,
    DEAD_LETTER_ROOT,
    S3_CONNECT_TIMEOUT_SECONDS,
    S3_REQUEST_TIMEOUT_SECONDS,
)
from bluesky_ingestion_jetstream.schemas.arrow_schemas import RECORD_TYPE_TO_SCHEMA
from bluesky_ingestion_jetstream.telemetry.instruments import record_dead_letter, record_dropped
from lib.timestamp_utils import CREATED_AT_FORMAT

logger = logging.getLogger(__name__)


class DeadLetterError(RuntimeError):
    """Raised when a batch could not be written to the dead letter either."""


def build_filesystem() -> S3FileSystem:
    """S3 filesystem with the same bounds as the commit path.

    Unbounded here would defeat the point: this write happens while the read loop
    is already stalled by a failed commit.
    """

    return S3FileSystem(
        region=AWS_REGION,
        connect_timeout=S3_CONNECT_TIMEOUT_SECONDS,
        request_timeout=S3_REQUEST_TIMEOUT_SECONDS,
    )


def build_path(
    record_type: str, run_id: str, now: datetime | None = None, root: str | None = None
) -> str:
    """Where one dead-lettered batch lands.

    Partitioned by record type and then by day so a recovery can read one day of
    one table rather than listing the whole prefix, and `dt=` spelled Hive-style
    so Athena or a crawler can be pointed at it without moving anything. The
    timestamp uses the repo's zero-padded format, so files sort chronologically;
    `run_id` names the process that gave up.

    The random suffix is not decoration. The timestamp resolves only to the
    second, and S3 has no "create if absent" -- two dead letters landing in the
    same second would silently overwrite each other, destroying unrecovered data,
    which is the one thing this module exists to prevent.
    """

    now = now or datetime.now(UTC)
    root = root or DEAD_LETTER_ROOT
    day = now.strftime("%Y-%m-%d")
    timestamp = now.strftime(CREATED_AT_FORMAT)
    return f"{root}/{record_type}/dt={day}/{timestamp}-{run_id}-{uuid4().hex[:8]}.parquet"


def build_table(record_type: str, rows: list[dict]) -> pa.Table:
    """Arrow table from the declared schema, independent of the catalog."""

    return pa.Table.from_pylist(rows, schema=RECORD_TYPE_TO_SCHEMA[record_type])


def write_dead_letter(
    record_type: str,
    rows: list[dict],
    run_id: str,
    filesystem: FileSystem | None = None,
    root: str | None = None,
) -> str:
    """Persist a batch that could not be committed, and return where it went.

    Attempted twice, then given up on. Holding the rows in memory until S3
    recovers would convert a transient failure into unbounded buffer growth and
    eventually a crash, which loses every buffered batch rather than this one.
    """

    filesystem = filesystem or build_filesystem()
    path = build_path(record_type, run_id, root=root)
    table = build_table(record_type, rows)

    for attempt in (1, 2):
        try:
            pq.write_table(table, path, filesystem=filesystem, compression="zstd")
        except Exception:
            logger.warning(
                "dead letter write failed (attempt %d/2) for %d %s rows at %s",
                attempt,
                len(rows),
                record_type,
                path,
                exc_info=True,
            )
        else:
            logger.error(
                "DEAD LETTER: %d %s rows are not in Iceberg; written to %s",
                len(rows),
                record_type,
                path,
            )
            record_dead_letter(record_type, len(rows))
            return path

    # Both the commit and its fallback failed, which in practice means S3 itself
    # is unreachable. Nothing durable is left to try.
    record_dropped(record_type, len(rows))
    raise DeadLetterError(
        f"dropped {len(rows)} {record_type} rows: dead letter write to {path} failed twice"
    )
