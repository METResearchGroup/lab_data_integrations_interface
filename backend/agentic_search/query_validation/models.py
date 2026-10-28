"""Types the validators share."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from backend.agentic_search.query_validation.query_intent.models import QueryIntent


class ValidationIssue(StrEnum):
    NONSENSE = "nonsense"
    UNKNOWN_RECORD_TYPE = "unknown_record_type"
    UNKNOWN_COLUMN = "unknown_column"
    RANGE_OUTSIDE_COVERAGE = "range_outside_coverage"
    KEYWORDS_REQUIRE_POSTS = "keywords_require_posts"
    KEYWORDS_REQUIRE_BOUNDED_RANGE = "keywords_require_bounded_range"
    EMPTY_KEYWORD = "empty_keyword"
    TOO_MANY_KEYWORDS = "too_many_keywords"
    KEYWORD_TOO_LONG = "keyword_too_long"


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    issues: list[ValidationIssue]
    intent: QueryIntent


@dataclass(frozen=True)
class TableMetadata:
    columns: tuple[str, ...]
    coverage_start: date
    coverage_end: date
