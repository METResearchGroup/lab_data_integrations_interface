"""Runs the validators and collects their issues."""

from __future__ import annotations

from backend.agentic_search.query_validation.models import (
    TableMetadata,
    ValidationResult,
)
from bluesky_ingestion_jetstream.constants import RecordType

CATALOG_SNAPSHOT_TTL_SECONDS = 300.0


def load_snapshot() -> dict[RecordType, TableMetadata]:
    """Columns from the Arrow schemas, coverage from Iceberg. Cached for the TTL."""

    raise NotImplementedError


def validate_query(query: str) -> ValidationResult:
    """Validate a natural-language query against what the tables hold."""

    raise NotImplementedError
