"""Iceberg write path -- one ``append`` per flush batch per table.

Every append is a full Iceberg commit: data files, then a manifest, then a
manifest list, then a new ``metadata.json``, then a Glue ``UpdateTable`` to swap
the pointer. Ten flushes across four tables therefore produce forty commits,
which is precisely the small-files regime this experiment exists to price.
"""

from __future__ import annotations

from typing import Any

from experimentation.iceberg.raw_writer import build_arrow


def append_batch(table: Any, rows: list[dict[str, Any]]) -> int:
    """Append one flush batch to its table. Returns the row count committed.

    Builds the Arrow table from ``table.schema()`` -- the ids the catalog
    actually assigned -- not from the declared schema. Iceberg matches columns
    by field id, so using the declared ids would stamp the Parquet footers with
    ids the table metadata does not know about, and every such column would read
    back as NULL. See the field-id note in ``schemas.py``.
    """
    arrow_table = build_arrow(table.schema().as_arrow(), rows)
    table.append(arrow_table)
    return len(rows)


def table_file_stats(table: Any) -> dict[str, Any]:
    """Current-snapshot file count and total size, read from table metadata.

    Uses ``inspect.files()`` rather than an S3 listing so it reflects what
    Iceberg believes it owns, not what happens to be sitting in the bucket.
    """
    table.refresh()
    if table.current_snapshot() is None:
        return {"file_count": 0, "total_bytes": 0, "record_count": 0}

    files = table.inspect.files()
    sizes = files.column("file_size_in_bytes").to_pylist() if files.num_rows else []
    records = files.column("record_count").to_pylist() if files.num_rows else []
    return {
        "file_count": len(sizes),
        "total_bytes": sum(sizes),
        "record_count": sum(records),
        "avg_file_bytes": (sum(sizes) / len(sizes)) if sizes else 0,
    }


def snapshot_count(table: Any) -> int:
    table.refresh()
    return len(table.snapshots())
