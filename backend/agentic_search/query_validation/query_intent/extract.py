"""Turns a natural-language query into a QueryIntent. The one LLM call."""

from __future__ import annotations

from datetime import UTC, date, datetime

from backend.agentic_search.query_validation.models import TableMetadata
from backend.agentic_search.query_validation.query_intent.models import (
    MAX_KEYWORD_LENGTH,
    MAX_KEYWORDS,
    QueryIntent,
)
from backend.agentic_search.query_validation.query_intent.prompts import (
    EXTRACT_USER_QUERY_INTENT_PROMPT,
)
from bluesky_ingestion_jetstream.constants import RecordType
from ml_tooling.llm.llm import structured_chat_completion


def _utc_today() -> date:
    """The current calendar date in UTC."""

    return datetime.now(UTC).date()


def _render_catalog(snapshot: dict[RecordType, TableMetadata]) -> str:
    return "\n".join(
        f"{record_type.value} ({meta.coverage_start} to {meta.coverage_end}): "
        f"{', '.join(meta.columns)}"
        for record_type, meta in snapshot.items()
    )


def _system_prompt(snapshot: dict[RecordType, TableMetadata]) -> str:
    return EXTRACT_USER_QUERY_INTENT_PROMPT.format(
        today=_utc_today(),
        catalog=_render_catalog(snapshot),
        max_keywords=MAX_KEYWORDS,
        max_keyword_length=MAX_KEYWORD_LENGTH,
    )


def _fill_open_end(intent: QueryIntent) -> QueryIntent:
    """Set a missing keyword end date to the current UTC date.

    The question stated a start and no end. A question with neither date
    is left unchanged, and validation refuses it.
    """

    if not intent.keywords or intent.start_date is None or intent.end_date is not None:
        return intent
    return intent.model_copy(update={"end_date": _utc_today(), "end_date_inferred": True})


def extract_intent(query: str, snapshot: dict[RecordType, TableMetadata]) -> QueryIntent:
    intent = structured_chat_completion(
        user_prompt=query,
        output_schema=QueryIntent,
        system_prompt=_system_prompt(snapshot),
    )
    return _fill_open_end(intent)
