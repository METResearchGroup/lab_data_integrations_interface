"""The Iceberg append itself, with no retry policy of its own.

One `append` is a whole commit: data files to S3, then a manifest, then a
manifest list, then a new `metadata.json`, then a Glue `UpdateTable` that swaps
the pointer. Only that last step makes anything visible, so a commit either lands
whole or not at all -- there is no partial table for a caller to repair. That is
what makes retrying the entire call the right unit, and it is why this module
exposes a single attempt and leaves the retrying to `sinks/iceberg.py`.

The cost of an abandoned attempt is the data files it already wrote. They are
unreferenced, invisible to every reader, and still billed until orphan cleanup
removes them.
"""

import pyarrow as pa
from pyiceberg.table import Table

from bluesky_ingestion_jetstream.aws.constants import FLUSH_ID_PROPERTY


def build_arrow(table: Table, rows: list[dict]) -> pa.Table:
    """Build the Arrow table to append, using the ids the catalog assigned.

    The schema comes from `table.schema()`, never from the declared module
    schema. Iceberg resolves columns by field id rather than by name, so ids that
    disagree with the table's do not raise -- the file is written, and every
    affected column reads back as NULL. Taking the schema from the table itself
    removes the failure mode rather than guarding against it.
    """

    return pa.Table.from_pylist(rows, schema=table.schema().as_arrow())


def append_once(table: Table, arrow: pa.Table, flush_id: str) -> None:
    """Attempt one commit, tagged so a retry can recognise its own work.

    Nothing is caught here. The caller decides what is worth retrying.
    """

    table.append(arrow, snapshot_properties={FLUSH_ID_PROPERTY: flush_id})


def already_committed(table: Table, flush_id: str) -> bool:
    """Whether this flush is already in the table's snapshot history.

    Covers the one case retrying cannot otherwise distinguish: the Glue update
    succeeded and the response was lost. The client sees a failure, retries, and
    -- because it reloads fresh metadata, which satisfies the optimistic-locking
    check -- commits the same rows a second time. Iceberg does not deduplicate,
    so those rows would both be returned by every query from then on.

    `refresh()` is a Glue `GetTable`, paid only on a retry.
    """

    table.refresh()
    return any(
        snapshot.summary is not None and snapshot.summary.get(FLUSH_ID_PROPERTY) == flush_id
        for snapshot in table.snapshots()
    )
