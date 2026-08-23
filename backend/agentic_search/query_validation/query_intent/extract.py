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

Set is_nonsense when the input is not a coherent question about Bluesky data.

Otherwise resolve it: pick the one record type it asks about, list the columns
it asks for, and resolve relative dates against today. Leave a date null when
the question does not bound that side.

Report what the question asks for, not the closest thing the tables happen to
hold. List every column it asks for even when no table above has that column,
under the name the question used, and never swap in a similar one. Leave
record_type null when no table holds the kind of record being asked for.

Do not add columns the question does not ask for.
"""


def _render_catalog(snapshot: dict[RecordType, TableMetadata]) -> str:
    return "\n".join(
        f"{record_type.value} ({meta.coverage_start} to {meta.coverage_end}): "
        f"{', '.join(meta.columns)}"
        for record_type, meta in snapshot.items()
    )


def extract_intent(query: str, snapshot: dict[RecordType, TableMetadata]) -> QueryIntent:
    return structured_chat_completion(
        user_prompt=query,
        output_schema=QueryIntent,
        system_prompt=SYSTEM_PROMPT.format(
            today=date.today(),
            catalog=_render_catalog(snapshot),
        ),
    )
