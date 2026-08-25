"""What generation hands back."""

from __future__ import annotations

from dataclasses import dataclass

from bluesky_ingestion_jetstream.constants import RecordType


@dataclass(frozen=True)
class GeneratedQuery:
    sql: str
    # Names the schema a CSV conversion formats against.
    record_type: RecordType
