import time
from dataclasses import dataclass

import pyarrow as pa

from bluesky_backfill_app.aws.queue import Message
from bluesky_backfill_app.fetch_repos.constants import (
    FLUSH_REASON_AGE,
    FLUSH_REASON_SIZE,
    MAX_BUFFER_AGE_SECONDS,
    MAX_BUFFER_SIZE_BYTES,
)
from bluesky_ingestion_jetstream.constants import RECORD_TYPES, RecordType


class RepoBuffer:
    """Arrow tables per record type, one per repo, plus the messages to ack. Flushed together."""

    def __init__(
        self,
        max_size_bytes: int = MAX_BUFFER_SIZE_BYTES,
        max_age_seconds: float = MAX_BUFFER_AGE_SECONDS,
    ) -> None:
        self.tables: dict[RecordType, list[pa.Table]] = {
            record_type: [] for record_type in RECORD_TYPES
        }
        self.messages: list[Message] = []
        self.dids: set[str] = set()
        self.size = 0
        self.max_size_bytes = max_size_bytes
        self.max_age_seconds = max_age_seconds
        self.oldest_received_at: float | None = None

    def add(
        self,
        message: Message,
        tables: dict[RecordType, pa.Table],
        received_at: float,
    ) -> None:
        """Buffer one repo. `received_at` is `time.monotonic()` at receive.

        A DID already buffered keeps its message, to ack, but not its rows again.
        """

        if message.did not in self.dids:
            self.dids.add(message.did)
            for record_type, table in tables.items():
                if table.num_rows:
                    self.tables[record_type].append(table)
                    self.size += table.nbytes

        self.messages.append(message)
        if self.oldest_received_at is None:
            self.oldest_received_at = received_at

    def should_flush(self) -> bool:
        if self.oldest_received_at is None:
            return False
        return (
            self.size >= self.max_size_bytes
            or time.monotonic() - self.oldest_received_at >= self.max_age_seconds
        )

    def flush_reason(self) -> str:
        """Size wins when both have tripped."""

        if not self.should_flush():
            raise ValueError("no flush threshold has been hit")
        if self.size >= self.max_size_bytes:
            return FLUSH_REASON_SIZE
        return FLUSH_REASON_AGE

    def clear(self) -> None:
        """Rebinds rather than empties, so lists already handed to the writer survive."""

        self.tables = {record_type: [] for record_type in RECORD_TYPES}
        self.messages = []
        self.dids = set()
        self.size = 0
        self.oldest_received_at = None


@dataclass(frozen=True, slots=True)
class FlushSummary:
    """What one flush holds. `sizes` is in-memory Arrow bytes."""

    reason: str
    repos: int
    rows: dict[RecordType, int]
    sizes: dict[RecordType, int]


def get_flush_summary(buffer: RepoBuffer, reason: str) -> FlushSummary:
    """Call before `clear`, which zeroes the counts."""

    rows: dict[RecordType, int] = {}
    sizes: dict[RecordType, int] = {}
    for record_type, tables in buffer.tables.items():
        if tables:
            rows[record_type] = sum(table.num_rows for table in tables)
            sizes[record_type] = sum(table.nbytes for table in tables)

    return FlushSummary(reason=reason, repos=len(buffer.messages), rows=rows, sizes=sizes)
