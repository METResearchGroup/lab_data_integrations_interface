"""Runs the validators and collects their issues."""

from __future__ import annotations

from backend.agentic_search.catalog.snapshot import load_snapshot
from backend.agentic_search.query_validation.check_data_availability import (
    check_data_availability,
)
from backend.agentic_search.query_validation.check_data_types import check_data_types
from backend.agentic_search.query_validation.check_nonsense import check_nonsense
from backend.agentic_search.query_validation.models import ValidationResult
from backend.agentic_search.query_validation.query_intent.extract import extract_intent


def validate_query(query: str) -> ValidationResult:
    """Validate a natural-language query against what the tables hold."""

    snapshot = load_snapshot()
    intent = extract_intent(query, snapshot)

    issues = check_nonsense(intent)
    if not issues:
        issues += check_data_types(intent, snapshot)
        issues += check_data_availability(intent, snapshot)

    return ValidationResult(valid=not issues, issues=issues)
