"""Build a `CatalogSnapshot` from Glue and Iceberg metadata. Reads no data files."""

import threading
from datetime import UTC, date, datetime
from time import monotonic

from pyiceberg.table import Table

from backend.agentic_search.catalog.descriptions import TABLE_DESCRIPTIONS, describe_column
from backend.agentic_search.models import CatalogSnapshot, ColumnDescription, TableDescription
from bluesky_ingestion_jetstream.aws.catalog import build_catalog, load_tables
from bluesky_ingestion_jetstream.aws.constants import GLUE_DATABASE, PARTITION_FIELD_NAME

CATALOG_TTL_SECONDS = 30 * 60

_lock = threading.Lock()
_cached: CatalogSnapshot | None = None
_cached_at: float = 0.0


def _columns(table: Table, record_type: str) -> list[ColumnDescription]:
    return [
        ColumnDescription(
            name=field.name,
            type=str(field.field_type),
            description=describe_column(record_type, field.name),
        )
        for field in table.schema().fields
    ]


def _coverage(table: Table) -> tuple[date | None, date | None, int]:
    """(earliest day, latest day, row count), from manifest metadata."""

    if table.current_snapshot() is None:
        return None, None, 0

    days: list[date] = []
    row_count = 0

    for partition in table.inspect.partitions().to_pylist():
        # Merge-on-read: `record_count` still counts rows the dedup job deleted.
        row_count += partition["record_count"] - partition["position_delete_record_count"]

        day = (partition.get("partition") or {}).get(PARTITION_FIELD_NAME)
        if day is not None:
            days.append(day)

    return (min(days) if days else None, max(days) if days else None, row_count)


def build_snapshot(tables: dict[str, Table] | None = None) -> CatalogSnapshot:
    """Read the catalog now. Pass `tables` to build against something other than Glue."""

    tables = load_tables(build_catalog()) if tables is None else tables

    described = []
    for record_type, table in tables.items():
        earliest_day, latest_day, row_count = _coverage(table)
        described.append(
            TableDescription(
                database=GLUE_DATABASE,
                name=record_type,
                record_type=record_type,
                description=TABLE_DESCRIPTIONS.get(record_type),
                columns=_columns(table, record_type),
                earliest_day=earliest_day,
                latest_day=latest_day,
                row_count=row_count,
            )
        )

    return CatalogSnapshot(tables=described, captured_at=datetime.now(UTC))


def get_catalog(*, force_refresh: bool = False) -> CatalogSnapshot:
    """The snapshot, rebuilt at most once every `CATALOG_TTL_SECONDS`."""

    global _cached, _cached_at

    with _lock:
        expired = monotonic() - _cached_at >= CATALOG_TTL_SECONDS
        if force_refresh or _cached is None or expired:
            _cached = build_snapshot()
            _cached_at = monotonic()
        return _cached


def clear_cache() -> None:
    global _cached, _cached_at

    with _lock:
        _cached = None
        _cached_at = 0.0
