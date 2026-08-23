"""Checks the requested record type and columns exist."""

from __future__ import annotations

from backend.agentic_search.query_validation.models import TableMetadata, ValidationIssue
from backend.agentic_search.query_validation.query_intent.models import QueryIntent
from bluesky_ingestion_jetstream.constants import RecordType


def check_data_types(
    intent: QueryIntent,
    snapshot: dict[RecordType, TableMetadata],
) -> list[ValidationIssue]:
    # UNKNOWN_RECORD_TYPE when none resolved, leaving no columns to check against.
    metadata = snapshot.get(intent.record_type) if intent.record_type else None
    if metadata is None:
        return [ValidationIssue.UNKNOWN_RECORD_TYPE]

    # UNKNOWN_COLUMN when the record type is missing any requested column.
    if set(intent.columns) - set(metadata.columns):
        return [ValidationIssue.UNKNOWN_COLUMN]
    return []
