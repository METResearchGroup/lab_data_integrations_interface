"""Types the validators share."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from pydantic import BaseModel

from bluesky_ingestion_jetstream.constants import RecordType


class ValidationCode(StrEnum):
    NONSENSE = "nonsense"
    UNKNOWN_RECORD_TYPE = "unknown_record_type"
    UNKNOWN_COLUMN = "unknown_column"
    RANGE_OUTSIDE_COVERAGE = "range_outside_coverage"


class QueryIntent(BaseModel):
    is_nonsense: bool
    nonsense_reason: str | None = None
    # None when the query maps to no table we hold.
    record_type: RecordType | None = None
    columns: list[str] = []
    start_date: date | None = None
    end_date: date | None = None


@dataclass(frozen=True)
class ValidationIssue:
    code: ValidationCode
    message: str
    suggestion: str | None = None


@dataclass(frozen=True)
class TableMetadata:
    # Schema order, so messages listing them are deterministic.
    columns: tuple[str, ...]
    coverage_start: date
    coverage_end: date


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    intent: QueryIntent
    issues: list[ValidationIssue] = field(default_factory=list)
