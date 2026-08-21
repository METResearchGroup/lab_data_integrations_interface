"""Checks the requested dates fall inside the tables' coverage."""

from __future__ import annotations

from datetime import date

from backend.agentic_search.query_validation.models import (
    QueryIntent,
    TableMetadata,
    ValidationCode,
    ValidationIssue,
)
from bluesky_ingestion_jetstream.constants import RecordType

# A day below this many rows is backdated client-clock junk, not coverage.
# `MAX_CREATED_AT_BACKDATE` lets a bad client clock land a row a week early.
MIN_ROWS_PER_COVERED_DAY = 1000


def coverage_bounds(day_row_counts: dict[date, int]) -> tuple[date, date]:
    """First and last day holding real data. Interior gaps are not bounds."""

    covered = sorted(
        day for day, rows in day_row_counts.items() if rows >= MIN_ROWS_PER_COVERED_DAY
    )
    if not covered:
        raise ValueError(f"no day holds {MIN_ROWS_PER_COVERED_DAY} rows")

    return covered[0], covered[-1]


def check_date_range(
    intent: QueryIntent, snapshot: dict[RecordType, TableMetadata]
) -> list[ValidationIssue]:
    # An unresolved record type is already reported by the column check.
    if intent.record_type is None:
        return []

    metadata = snapshot[intent.record_type]
    # An open bound asks for as far as we go, so it cannot fall outside.
    start = intent.start_date or metadata.coverage_start
    end = intent.end_date or metadata.coverage_end

    if start >= metadata.coverage_start and end <= metadata.coverage_end:
        return []

    overlaps = start <= metadata.coverage_end and end >= metadata.coverage_start
    clamped_start = max(start, metadata.coverage_start)
    clamped_end = min(end, metadata.coverage_end)

    return [
        ValidationIssue(
            code=ValidationCode.RANGE_OUTSIDE_COVERAGE,
            message=(
                f"{intent.record_type} is covered from {metadata.coverage_start} to "
                f"{metadata.coverage_end}, not {start} to {end}"
            ),
            suggestion=f"try {clamped_start} to {clamped_end}" if overlaps else None,
        )
    ]
