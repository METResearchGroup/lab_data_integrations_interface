"""Turns a natural-language query into a QueryIntent. The one LLM call."""

from __future__ import annotations

from backend.agentic_search.query_validation.models import TableMetadata
from backend.agentic_search.query_validation.query_intent.dates import resolve_dates
from backend.agentic_search.query_validation.query_intent.models import (
    MAX_KEYWORD_LENGTH,
    MAX_KEYWORDS,
    QueryIntent,
)
from backend.agentic_search.query_validation.query_intent.prompts import (
    EXTRACT_USER_QUERY_INTENT_PROMPT,
)
from bluesky_ingestion_jetstream.constants import RecordType
from lib.timestamp_utils import get_current_date
from ml_tooling.llm.llm import structured_chat_completion


def _render_catalog(snapshot: dict[RecordType, TableMetadata]) -> str:
    return "\n".join(
        f"{record_type.value}: "
        f"{', '.join(meta.columns)}"
        for record_type, meta in snapshot.items()
    )


def _system_prompt(snapshot: dict[RecordType, TableMetadata]) -> str:
    return EXTRACT_USER_QUERY_INTENT_PROMPT.format(
        today=get_current_date(),
        catalog=_render_catalog(snapshot),
        max_keywords=MAX_KEYWORDS,
        max_keyword_length=MAX_KEYWORD_LENGTH,
    )


def extract_intent(query: str, snapshot: dict[RecordType, TableMetadata]) -> QueryIntent:
    intent = structured_chat_completion(
        user_prompt=query,
        output_schema=QueryIntent,
        system_prompt=_system_prompt(snapshot),
    )
    if intent.is_nonsense:
        return intent
    resolved = resolve_dates(query, intent.start_date, intent.end_date)
    return intent.model_copy(
        update={
            "start_date": resolved.start_date,
            "end_date": resolved.end_date,
            "start_date_inferred": resolved.start_date_inferred,
            "end_date_inferred": resolved.end_date_inferred,
        }
    )
