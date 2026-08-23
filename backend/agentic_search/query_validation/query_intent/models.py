"""The structured form of a natural-language query."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from bluesky_ingestion_jetstream.constants import RecordType


class QueryIntent(BaseModel):
    """What the query asks for. Pydantic because the LLM fills it in directly.

    Unverified: every field is the model's proposal, not a fact about the tables.
    """

    is_nonsense: bool
    record_type: RecordType | None
    columns: list[str] = Field(default_factory=list)
    start_date: date | None
    end_date: date | None
