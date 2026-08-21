"""Checks the requested columns exist."""

from __future__ import annotations

from backend.agentic_search.query_validation.models import (
    QueryIntent,
    TableMetadata,
    ValidationIssue,
)
from bluesky_ingestion_jetstream.constants import RecordType


def check_columns(
    intent: QueryIntent, snapshot: dict[RecordType, TableMetadata]
) -> list[ValidationIssue]:
    # One UNKNOWN_COLUMN per requested column the record type does not have.
    # Nothing to check against when no record type resolved.
    raise NotImplementedError
