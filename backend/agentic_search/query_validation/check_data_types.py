"""Checks the requested record type and columns exist."""

from __future__ import annotations

from backend.agentic_search.query_validation.models import TableMetadata, ValidationIssue
from bluesky_ingestion_jetstream.constants import RecordType


def check_data_types(
    record_type: RecordType | None,
    columns: list[str],
    snapshot: dict[RecordType, TableMetadata],
) -> list[ValidationIssue]:
    # UNKNOWN_RECORD_TYPE when none resolved, leaving no columns to check against.
    # UNKNOWN_COLUMN when the record type is missing any requested column.
    raise NotImplementedError
