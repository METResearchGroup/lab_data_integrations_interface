"""Checks the requested record type and columns exist."""

from __future__ import annotations

from backend.agentic_search.query_validation.models import TableMetadata, ValidationIssue
from backend.agentic_search.query_validation.query_intent.models import QueryIntent
from bluesky_ingestion_jetstream.constants import RecordType


def check_data_types(
    intent: QueryIntent,
    snapshot: dict[RecordType, TableMetadata],
) -> list[ValidationIssue]:
    """
    Checks that we have the requested table and column in our DB

    UNKNOWN_RECORD_TYPE when table doesn't match any tables in our DB
    UNKNOWN_COLUMN when column doesn't match any columns within the requested table
    """
    metadata = snapshot.get(intent.record_type) if intent.record_type else None
    if metadata is None:
        return [ValidationIssue.UNKNOWN_RECORD_TYPE]

    if set(intent.columns) - set(metadata.columns):
        return [ValidationIssue.UNKNOWN_COLUMN]
    return []
