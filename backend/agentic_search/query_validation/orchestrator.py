"""Runs the validators and collects their issues."""

from __future__ import annotations

from datetime import date

from backend.agentic_search.query_validation.check_data_availability import (
    check_data_availability,
)
from backend.agentic_search.query_validation.check_data_types import check_data_types
from backend.agentic_search.query_validation.check_nonsense import check_nonsense
from backend.agentic_search.query_validation.models import TableMetadata, ValidationResult
from backend.agentic_search.query_validation.query_intent.extract import extract_intent
from backend.agentic_search.query_validation.query_intent.models import QueryIntent
from bluesky_ingestion_jetstream.constants import DATA_START_DATE, RecordType
from bluesky_ingestion_jetstream.schemas.arrow_schemas import RECORD_TYPE_TO_SCHEMA


def build_snapshot() -> dict[RecordType, TableMetadata]:
    """
    Returns columns and date range for each table in Iceberg
    """

    today = date.today()
    return {
        record_type: TableMetadata(
            columns=tuple(schema.names),
            coverage_start=DATA_START_DATE,
            coverage_end=today,
        )
        for record_type, schema in RECORD_TYPE_TO_SCHEMA.items()
    }


def validate_intent(
    intent: QueryIntent,
    snapshot: dict[RecordType, TableMetadata],
) -> ValidationResult:
    issues = check_nonsense(intent)
    if not issues:
        issues += check_data_types(intent, snapshot)
        issues += check_data_availability(intent, snapshot)

    return ValidationResult(valid=not issues, issues=issues)


def validate_query(query: str) -> ValidationResult:
    """Validate a natural-language query against what the tables hold."""

    snapshot = build_snapshot()
    return validate_intent(extract_intent(query, snapshot), snapshot)
