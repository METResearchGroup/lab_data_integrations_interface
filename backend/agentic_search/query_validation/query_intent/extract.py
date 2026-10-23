"""Turns a natural-language query into a QueryIntent. The one LLM call."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from backend.agentic_search.query_validation.models import TableMetadata
from backend.agentic_search.query_validation.query_intent.models import (
    MAX_KEYWORD_LENGTH,
    MAX_KEYWORDS,
    QueryIntent,
)
from bluesky_ingestion_jetstream.constants import RecordType
from ml_tooling.llm.llm import structured_chat_completion

_PROMPT_PATH = Path(__file__).parent / "prompts" / "extract_system.txt"


def _render_catalog(snapshot: dict[RecordType, TableMetadata]) -> str:
    return "\n".join(
        f"{record_type.value} ({meta.coverage_start} to {meta.coverage_end}): "
        f"{', '.join(meta.columns)}"
        for record_type, meta in snapshot.items()
    )


def _system_prompt(snapshot: dict[RecordType, TableMetadata]) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return template.format(
        today=date.today(),
        catalog=_render_catalog(snapshot),
        max_keywords=MAX_KEYWORDS,
        max_keyword_length=MAX_KEYWORD_LENGTH,
    )


def extract_intent(query: str, snapshot: dict[RecordType, TableMetadata]) -> QueryIntent:
    return structured_chat_completion(
        user_prompt=query,
        output_schema=QueryIntent,
        system_prompt=_system_prompt(snapshot),
    )
