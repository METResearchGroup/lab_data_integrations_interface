import time

from bluesky_backfill_app.aws.queue import Message
from bluesky_backfill_app.fetch_repos.constants import (
    FLUSH_REASON_AGE,
    FLUSH_REASON_SIZE,
    MAX_BUFFER_AGE_SECONDS,
    MAX_BUFFER_SIZE_BYTES,
)
from bluesky_ingestion_jetstream.constants import RECORD_TYPES, RecordType
from bluesky_ingestion_jetstream.storage.buffer import Buffer


class RepoBuffer:
    """One row buffer per record type, plus the messages to ack. Flushed together."""

    def __init__(
        self,
        max_size_bytes: int = MAX_BUFFER_SIZE_BYTES,
        max_age_seconds: float = MAX_BUFFER_AGE_SECONDS,
    ) -> None:
        self.buffers = {record_type: Buffer() for record_type in RECORD_TYPES}
        self.messages: list[Message] = []
        self.max_size_bytes = max_size_bytes
        self.max_age_seconds = max_age_seconds
        self.oldest_received_at: float | None = None

    @property
    def size(self) -> int:
        return sum(buffer.size for buffer in self.buffers.values())

    def add(
        self,
        message: Message,
        rows: dict[RecordType, list[dict]],
        received_at: float,
    ) -> None:
        """Buffer one repo. `received_at` is `time.monotonic()` at receive."""

        for record_type, type_rows in rows.items():
            buffer = self.buffers[record_type]
            for row in type_rows:
                buffer.add(row)

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
        for buffer in self.buffers.values():
            buffer.clear()
        self.messages = []
        self.oldest_received_at = None
