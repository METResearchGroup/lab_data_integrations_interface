"""Table columns and coverage, read from Iceberg metadata."""

from __future__ import annotations

import logging
import threading
import time

from pyiceberg.table import Table

from backend.agentic_search.query_validation.models import TableMetadata
from bluesky_ingestion_jetstream.aws.catalog import build_catalog, load_tables
from bluesky_ingestion_jetstream.aws.constants import PARTITION_FIELD_NAME
from bluesky_ingestion_jetstream.constants import RecordType

logger = logging.getLogger(__name__)

CATALOG_SNAPSHOT_TTL_SECONDS = 30.0 * 60.0

_lock = threading.Lock()
_cached: dict[RecordType, TableMetadata] | None = None
_expires_at = 0.0


def _table_metadata(table: Table) -> TableMetadata | None:
    partitions = table.inspect.partitions().to_pylist()
    days = [row["partition"][PARTITION_FIELD_NAME] for row in partitions]
    if not days:
        return None

    return TableMetadata(
        columns=tuple(field.name for field in table.schema().fields),
        coverage_start=min(days),
        coverage_end=max(days),
    )


def build_snapshot() -> dict[RecordType, TableMetadata]:
    """Uncached, and slow: tens of seconds."""

    tables = load_tables(build_catalog())
    snapshot: dict[RecordType, TableMetadata] = {}

    for record_type, table in tables.items():
        metadata = _table_metadata(table)
        if metadata is None:
            logger.info("Table %s holds no data; omitting from the snapshot.", record_type)
            continue
        snapshot[record_type] = metadata

    return snapshot


def load_snapshot(*, force_refresh: bool = False) -> dict[RecordType, TableMetadata]:
    """Cached for the TTL. A failed refresh serves the stale snapshot; a cold start raises."""

    global _cached, _expires_at

    with _lock:
        if not force_refresh and _cached is not None and time.monotonic() < _expires_at:
            return _cached

        try:
            snapshot = build_snapshot()
        except Exception:
            if _cached is None:
                raise
            logger.exception("Catalog snapshot refresh failed; serving the stale snapshot.")
            return _cached

        _cached = snapshot
        _expires_at = time.monotonic() + CATALOG_SNAPSHOT_TTL_SECONDS
        return snapshot


def reset_cache() -> None:
    global _cached, _expires_at
    with _lock:
        _cached = None
        _expires_at = 0.0
