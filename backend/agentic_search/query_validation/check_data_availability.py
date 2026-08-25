"""Checks the requested dates fall inside the tables' coverage."""

from __future__ import annotations

from datetime import date

from backend.agentic_search.query_validation.models import TableMetadata, ValidationIssue
from backend.agentic_search.query_validation.query_intent.models import QueryIntent
from bluesky_ingestion_jetstream.constants import RecordType


def _coverage(
    record_type: RecordType | None,
    snapshot: dict[RecordType, TableMetadata],
) -> tuple[date, date] | None:
    """The record type's bounds, or the widest bounds when none resolved."""

    metadata = snapshot.get(record_type) if record_type else None
    if metadata is not None:
        return metadata.coverage_start, metadata.coverage_end
    if not snapshot:
        return None
    return (
        min(meta.coverage_start for meta in snapshot.values()),
        max(meta.coverage_end for meta in snapshot.values()),
    )


def check_data_availability(
    intent: QueryIntent,
    snapshot: dict[RecordType, TableMetadata],
) -> list[ValidationIssue]:
    """
    Checks if requested data is in range of DATA_START_DATE and today

    RANGE_OUTSIDE_COVERAGE when either requested date leaves the coverage bounds.
    """

    coverage = _coverage(intent.record_type, snapshot)
    if coverage is None:
        return []

    coverage_start, coverage_end = coverage
    starts_early = intent.start_date is not None and intent.start_date < coverage_start
    ends_late = intent.end_date is not None and intent.end_date > coverage_end
    if starts_early or ends_late:
        return [ValidationIssue.RANGE_OUTSIDE_COVERAGE]
    return []
