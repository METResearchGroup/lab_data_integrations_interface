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

Set is_nonsense only when the input is not a coherent question about Bluesky
data. A coherent question about records we do not hold is not nonsense.

Otherwise: pick the one record type it asks about, list every column it asks
for, and resolve its dates against today. Leave a date null only when the
question does not bound that side.

Report what the question asks for, not the closest thing the tables hold.
Never swap in a similar record type or column for an absent one, and do not
add columns the question does not ask for.

Worked examples, for a catalog holding likes (uri, subject_uri) and follows
(uri, subject_did), where today is 2026-06-10:

  "zxcvb qwerty"
    is_nonsense=true record_type=null columns=[] start=null end=null
  "list every block someone made"
    is_nonsense=false record_type=null columns=[] start=null end=null
  "likes from the last three days"
    is_nonsense=false record_type=likes columns=["uri"] start=2026-06-07 end=2026-06-10
  "follows with their vanity handles"
    is_nonsense=false record_type=follows columns=["subject_did","vanity handles"]
    start=null end=null
  "likes from February 2024"
    is_nonsense=false record_type=likes columns=["uri"] start=2024-02-01 end=2024-02-29
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
