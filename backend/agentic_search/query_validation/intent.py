"""Extracts the query intent and flags nonsense. The one LLM call."""

from __future__ import annotations

from backend.agentic_search.query_validation.models import (
    QueryIntent,
    ValidationIssue,
)

SYSTEM_PROMPT = ""


def extract_intent(query: str) -> QueryIntent:
    raise NotImplementedError


def check_intent(intent: QueryIntent) -> list[ValidationIssue]:
    raise NotImplementedError
