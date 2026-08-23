"""Checks the query is a coherent question about our data."""

from __future__ import annotations

from backend.agentic_search.query_validation.models import ValidationIssue
from backend.agentic_search.query_validation.query_intent.models import QueryIntent


def check_nonsense(intent: QueryIntent) -> list[ValidationIssue]:
    return [ValidationIssue.NONSENSE] if intent.is_nonsense else []
