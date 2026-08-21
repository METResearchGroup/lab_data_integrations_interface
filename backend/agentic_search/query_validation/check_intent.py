"""Checks the query is a coherent question about our data."""

from __future__ import annotations

from backend.agentic_search.query_validation.models import ValidationIssue

SYSTEM_PROMPT = ""


def check_nonsense(query: str) -> list[ValidationIssue]:
    # NONSENSE when the query is not answerable from a record type we hold.
    raise NotImplementedError
