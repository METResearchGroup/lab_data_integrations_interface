"""Checks the requested record type and columns exist."""

from __future__ import annotations

from difflib import get_close_matches

from backend.agentic_search.query_validation.models import (
    QueryIntent,
    TableMetadata,
    ValidationCode,
    ValidationIssue,
)
from bluesky_ingestion_jetstream.constants import RecordType

# Cutoff for "did you mean", passed to difflib.
COLUMN_SUGGESTION_CUTOFF = 0.6


def normalize(columns: list[str]) -> list[str]:
    """Lowercased and deduped, in the order asked for."""

    return list(dict.fromkeys(column.strip().lower() for column in columns))


def suggest(
    column: str, record_type: RecordType, snapshot: dict[RecordType, TableMetadata]
) -> str | None:
    """The nearest repair: another record type holding the column, else a typo fix."""

    elsewhere = [
        other
        for other, metadata in snapshot.items()
        if other != record_type and column in metadata.columns
    ]
    if elsewhere:
        return f"{column} is on {', '.join(elsewhere)}, not {record_type}"

    close = get_close_matches(
        column, snapshot[record_type].columns, n=1, cutoff=COLUMN_SUGGESTION_CUTOFF
    )
    return f"did you mean {close[0]}?" if close else None


def check_columns(
    intent: QueryIntent, snapshot: dict[RecordType, TableMetadata]
) -> list[ValidationIssue]:
    if intent.record_type is None:
        return [
            ValidationIssue(
                code=ValidationCode.UNKNOWN_RECORD_TYPE,
                message="the query does not map to a record type we hold",
                suggestion=f"we hold {', '.join(snapshot)}",
            )
        ]

    known = snapshot[intent.record_type].columns
    return [
        ValidationIssue(
            code=ValidationCode.UNKNOWN_COLUMN,
            message=f"{intent.record_type} has no column {column}",
            suggestion=suggest(column, intent.record_type, snapshot)
            or f"columns are {', '.join(known)}",
        )
        for column in normalize(intent.columns)
        if column not in known
    ]
