"""Turns a natural-language query into a QueryIntent. The one LLM call."""

from __future__ import annotations

from datetime import date

from backend.agentic_search.query_validation.models import TableMetadata
from backend.agentic_search.query_validation.query_intent.models import QueryIntent
from bluesky_ingestion_jetstream.constants import RecordType
from ml_tooling.llm.llm import structured_chat_completion

SYSTEM_PROMPT = """Map the user's question onto our Bluesky tables.

Today is {today}.

Tables, their columns, and the dates they cover:
{catalog}

Set is_nonsense when the question cannot be answered from these tables at all.

Otherwise resolve it: pick the one record type it asks about, list only the
columns it needs, and resolve relative dates against today. Leave a date null
when the question does not bound that side.

Leave record_type null when the question is about our data but does not say
which table. Name only columns the question needs; do not invent one to fill
the field.
"""


def _render_catalog(snapshot: dict[RecordType, TableMetadata]) -> str:
    return "\n".join(
        f"{record_type.value} ({meta.coverage_start} to {meta.coverage_end}): "
        f"{', '.join(meta.columns)}"
        for record_type, meta in snapshot.items()
    )


def extract_intent(query: str, snapshot: dict[RecordType, TableMetadata]) -> QueryIntent:
    """Resolve the query against the catalog. The checks verify what comes back."""

    return structured_chat_completion(
        user_prompt=query,
        output_schema=QueryIntent,
        system_prompt=SYSTEM_PROMPT.format(
            today=date.today(),
            catalog=_render_catalog(snapshot),
        ),
    )
