"""Types the validators share."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class ValidationIssue(StrEnum):
    NONSENSE = "nonsense"
    UNKNOWN_RECORD_TYPE = "unknown_record_type"
    UNKNOWN_COLUMN = "unknown_column"
    RANGE_OUTSIDE_COVERAGE = "range_outside_coverage"


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    issues: list[ValidationIssue]


@dataclass(frozen=True)
class TableMetadata:
    columns: tuple[str, ...]
    coverage_start: date
    coverage_end: date
