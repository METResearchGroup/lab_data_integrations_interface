"""Checks the requested dates fall inside the tables' coverage."""

from __future__ import annotations

from backend.agentic_search.query_validation.models import (
    QueryIntent,
    TableMetadata,
    ValidationIssue,
)
from bluesky_ingestion_jetstream.constants import RecordType


def check_date_range(
    intent: QueryIntent, snapshot: dict[RecordType, TableMetadata]
) -> list[ValidationIssue]:
    # RANGE_OUTSIDE_COVERAGE when either requested date leaves the coverage bounds.
    # Widest bounds in the snapshot when no record type resolved.
    raise NotImplementedError
