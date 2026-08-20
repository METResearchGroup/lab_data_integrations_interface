"""Shared types for the agentic search pipeline: validation, SQL generation, execution."""

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Decision(StrEnum):
    """What validation concluded about a query."""

    ACCEPT = "accept"
    REJECT = "reject"
    NEEDS_NARROWING = "needs_narrowing"


class QueryScope(BaseModel):
    """What a natural-language query resolves to in catalog terms."""

    record_types: list[str] = Field(default_factory=list)
    start_day: date | None = None
    end_day: date | None = None
    keywords: list[str] = Field(default_factory=list)


class ColumnDescription(BaseModel):
    name: str
    type: str
    description: str | None = None


class TableDescription(BaseModel):
    database: str
    name: str
    record_type: str
    description: str | None = None
    columns: list[ColumnDescription]
    earliest_day: date | None = None
    latest_day: date | None = None
    row_count: int | None = None


class CatalogSnapshot(BaseModel):
    """What the warehouse held at `captured_at`."""

    tables: list[TableDescription]
    captured_at: datetime

    def get_table(self, name: str) -> TableDescription | None:
        return next((table for table in self.tables if table.name == name), None)
