"""The Iceberg append itself.

One `append` is a whole commit: data files to S3, then a manifest, then a
manifest list, then a new `metadata.json`, then a Glue `UpdateTable` that swaps
the pointer. Only that last step makes anything visible, so a commit either lands
whole or not at all -- there is no partial table for a caller to repair.
"""

import pyarrow as pa
from pyiceberg.table import Table

from bluesky_ingestion_jetstream.aws.constants import SNAPSHOT_FLUSH_ID_TAG


def build_append_table(table: Table, rows: list[dict]) -> pa.Table:
    """Build the table to append, using the schema the catalog assigned.

    Iceberg resolves columns by field id, so a declared schema whose ids have
    drifted from the table's does not raise -- the affected columns just read
    back as NULL.
    """

    return pa.Table.from_pylist(rows, schema=table.schema().as_arrow())


def append_once(table: Table, append_table: pa.Table, flush_id: str) -> None:
    table.append(append_table, snapshot_properties={SNAPSHOT_FLUSH_ID_TAG: flush_id})


def already_committed(table: Table, flush_id: str) -> bool:
    """Checks to see if a flush exists in the table's snapshot history."""

    table.refresh()
    return any(
        snapshot.summary is not None and snapshot.summary.get(SNAPSHOT_FLUSH_ID_TAG) == flush_id
        for snapshot in table.snapshots()
    )
