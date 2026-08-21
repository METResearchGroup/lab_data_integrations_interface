"""Checks the requested dates fall inside the tables' coverage."""

from __future__ import annotations

from datetime import date

from backend.agentic_search.query_validation.models import TableMetadata, ValidationIssue
from bluesky_ingestion_jetstream.constants import RecordType


def check_data_availability(
    record_type: RecordType | None,
    start_date: date | None,
    end_date: date | None,
    snapshot: dict[RecordType, TableMetadata],
) -> list[ValidationIssue]:
    # RANGE_OUTSIDE_COVERAGE when either requested date leaves the coverage bounds.
    # An open bound asks for as far as we go. Widest bounds without a record type.
    raise NotImplementedError
