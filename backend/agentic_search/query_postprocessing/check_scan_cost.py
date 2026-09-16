"""Estimates what a query scans, from Iceberg metadata, without running it.

Athena bills by bytes read ($5/TB), so bytes are the cap. Planning the same scan
in PyIceberg prunes the same partitions and files, and each data file records its
per-column sizes.
"""

from __future__ import annotations

from datetime import date, timedelta

from pyiceberg.schema import Schema
from pyiceberg.table import FileScanTask, Table

from backend.agentic_search.query_validation.query_intent.models import QueryIntent
from bluesky_ingestion_jetstream.aws.constants import PARTITION_SOURCE_COLUMN

BYTES_PER_GB = 2**30

# The cap set in docs/design_docs/2026-07-09_agentic_search_system_design.md.
MAX_SCAN_BYTES = 10 * BYTES_PER_GB


def _midnight(day: date) -> str:
    return f"{day.isoformat()}T00:00:00+00:00"


def _row_filter(intent: QueryIntent) -> str:
    """The bounds `generate_sql` writes into the WHERE clause. "True" scans everything."""

    conditions = []
    if intent.start_date is not None:
        conditions.append(f"{PARTITION_SOURCE_COLUMN} >= '{_midnight(intent.start_date)}'")
    if intent.end_date is not None:
        end = intent.end_date + timedelta(days=1)
        conditions.append(f"{PARTITION_SOURCE_COLUMN} < '{_midnight(end)}'")

    return " AND ".join(conditions) if conditions else "True"


def _leaf_ids(schema: Schema, columns: list[str]) -> set[int] | None:
    """Sizes are recorded per leaf column. None means every column is read."""

    if not columns:
        return None

    # WHERE and ORDER BY read the partition column too.
    selected = schema.select(*columns, PARTITION_SOURCE_COLUMN)
    return {
        field_id for field_id in selected.field_ids if selected.find_type(field_id).is_primitive
    }


def _task_bytes(task: FileScanTask, leaf_ids: set[int] | None) -> int:
    sizes = task.file.column_sizes or {}
    if leaf_ids is not None and leaf_ids.issubset(sizes):
        read = sum(sizes[field_id] for field_id in leaf_ids)
    else:
        read = task.file.file_size_in_bytes

    return read + sum(delete.file_size_in_bytes for delete in task.delete_files)


def estimate_scan_bytes(table: Table, intent: QueryIntent) -> int:
    leaf_ids = _leaf_ids(table.schema(), intent.columns)
    tasks = table.scan(row_filter=_row_filter(intent)).plan_files()
    return sum(_task_bytes(task, leaf_ids) for task in tasks)


def over_scan_limit(table: Table, intent: QueryIntent) -> str | None:
    """Why the query is too expensive to run, or None if it is within the cap."""

    scan_bytes = estimate_scan_bytes(table, intent)
    if scan_bytes <= MAX_SCAN_BYTES:
        return None

    return (
        f"the query scans about {scan_bytes / BYTES_PER_GB:.1f} GB, "
        f"over the {MAX_SCAN_BYTES / BYTES_PER_GB:.0f} GB limit; "
        "narrow the date range or ask for fewer columns"
    )
