"""In-memory buffers holding events between disk writes."""

import json
import time
from dataclasses import dataclass, field

from bluesky_ingestion_jetstream.constants import (
    FLUSH_REASON_AGE,
    FLUSH_REASON_SIZE,
    MAX_BUFFER_AGE_SECONDS,
    MAX_BUFFER_SIZE_BYTES,
    RECORD_TYPES,
)
from bluesky_ingestion_jetstream.sinks.base import Sink


def row_bytes(row: dict) -> int:
    """Serialized JSON size of a row, in bytes.

    `default=str` covers the datetime columns. Serialize once to measure, then
    discard the string -- the writer needs the dict, not the JSON.
    """

    return len(json.dumps(row, default=str).encode())


@dataclass
class Buffer:
    """Rows of a single record type.

    `size` is **serialized JSON bytes**, tracked incrementally because there is
    no O(1) way to read it back off the rows. It is a proxy, not a measurement of
    either endpoint: real heap runs higher, since each row is a dict of `str`
    objects carrying per-object overhead, while the Parquet file it produces is
    smaller, since Parquet dictionary-encodes and compresses.
    """

    rows: list[dict] = field(default_factory=list)
    size: int = 0

    def add(self, row: dict) -> None:
        """Add a row to the buffer."""

        self.rows.append(row)
        self.size += row_bytes(row)

    def clear(self) -> None:
        """Empty the buffer.

        Rebinds `rows` rather than mutating it in place, so a reference already
        handed to the writer is not emptied underneath it.
        """

        self.rows = []
        self.size = 0


class BufferSet:
    """One buffer per record type, flushed together.

    Decides *whether* to flush; writing to disk is the writer's job.
    """

    def __init__(
        self,
        max_size_bytes: int = MAX_BUFFER_SIZE_BYTES,
        max_age_seconds: float = MAX_BUFFER_AGE_SECONDS,
    ) -> None:
        self.buffers = {record_type: Buffer() for record_type in RECORD_TYPES}
        self.max_size_bytes = max_size_bytes
        self.max_age_seconds = max_age_seconds
        # monotonic, so an NTP correction cannot make the timer fire early.
        self.last_flush = time.monotonic()

    @property
    def size(self) -> int:
        """Serialized bytes held across every buffer.

        Summed from the children buffers rather than kept as another counter, so it
        cannot drift out of sync with them.
        """

        return sum(buffer.size for buffer in self.buffers.values())

    def add(self, record_type: str, row: dict) -> None:
        """Route a row to the buffer for its record type."""

        self.buffers[record_type].add(row)

    def should_flush(self) -> bool:
        """Whether the set has hit its size threshold or its max age."""

        if self.size == 0:
            return False
        return (
            self.size >= self.max_size_bytes
            or time.monotonic() - self.last_flush >= self.max_age_seconds
        )

    def flush_reason(self) -> str:
        """Which of the two thresholds tripped. Size wins when both have.

        Only meaningful once `should_flush` is true, and raises otherwise rather
        than naming a threshold that was never hit.
        """

        if not self.should_flush():
            raise ValueError("no flush threshold has been hit")
        if self.size >= self.max_size_bytes:
            return FLUSH_REASON_SIZE
        return FLUSH_REASON_AGE

    def mark_flushed(self) -> None:
        """Restart the age timer. Called after a flush, however it was triggered."""

        self.last_flush = time.monotonic()


@dataclass(frozen=True, slots=True)
class FlushSummary:
    """What one flush wrote, keyed by record type."""

    reason: str
    rows: dict[str, int]
    sizes: dict[str, int]


def get_flush_summary(buffers: BufferSet, reason: str) -> FlushSummary:
    """What the buffers hold. Call before `flush`, which zeroes both counts."""

    rows: dict[str, int] = {}
    sizes: dict[str, int] = {}

    for record_type, buffer in buffers.buffers.items():
        if buffer.rows:
            rows[record_type] = len(buffer.rows)
            sizes[record_type] = buffer.size

    return FlushSummary(reason=reason, rows=rows, sizes=sizes)


def flush(buffers: BufferSet, sink: Sink) -> None:
    """Write every non-empty buffer to the sink and empty it.

    Each buffer is cleared only after its write returns; clearing first would
    lose the batch if the write raised. A sink that dead-letters a batch has
    dealt with it and returns normally, so those rows are cleared too -- keeping
    them would write them twice on the next flush.
    """

    for record_type, buffer in buffers.buffers.items():
        if buffer.rows:
            sink.write(record_type, buffer.rows)
            buffer.clear()
    buffers.mark_flushed()
