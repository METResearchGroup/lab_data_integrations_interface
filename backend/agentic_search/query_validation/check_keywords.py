"""Checks a keyword filter is one we can run against post text."""

from __future__ import annotations

from backend.agentic_search.query_validation.models import ValidationIssue
from backend.agentic_search.query_validation.query_intent.models import (
    MAX_KEYWORD_LENGTH,
    MAX_KEYWORDS,
    QueryIntent,
)
from bluesky_ingestion_jetstream.constants import RecordType


def check_keywords(intent: QueryIntent) -> list[ValidationIssue]:
    """Refuse text filters that are not a bounded scan of posts.

    KEYWORDS_REQUIRE_POSTS when the filter targets anything but posts.
    KEYWORDS_REQUIRE_BOUNDED_RANGE when either date is open.
    EMPTY_KEYWORD when a term is blank.
    TOO_MANY_KEYWORDS and KEYWORD_TOO_LONG past the shared caps.
    An empty keyword list is no filter, and passes.
    """

    if not intent.keywords:
        return []

    terms = [keyword.strip() for keyword in intent.keywords]
    issues: list[ValidationIssue] = []
    if intent.record_type is not RecordType.POSTS:
        issues.append(ValidationIssue.KEYWORDS_REQUIRE_POSTS)
    if intent.start_date is None or intent.end_date is None:
        issues.append(ValidationIssue.KEYWORDS_REQUIRE_BOUNDED_RANGE)
    if any(not term for term in terms):
        issues.append(ValidationIssue.EMPTY_KEYWORD)
    if len(terms) > MAX_KEYWORDS:
        issues.append(ValidationIssue.TOO_MANY_KEYWORDS)
    if any(len(term) > MAX_KEYWORD_LENGTH for term in terms):
        issues.append(ValidationIssue.KEYWORD_TOO_LONG)
    return issues
