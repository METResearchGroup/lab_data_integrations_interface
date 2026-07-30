"""The contract between the buffers and wherever their rows end up.

Narrow on purpose. `storage/buffer.py` decides *when* to flush and holds the
rows; it should not know that the destination is Iceberg, or that it is remote,
or that a write can be retried. Keeping the seam here is what lets the buffer
tests run without pyiceberg, boto3, or a network.
"""

from typing import Protocol


class Sink(Protocol):
    """Somewhere a flush of one record type's rows can be written."""

    def write(self, record_type: str, rows: list[dict]) -> None:
        """Persist `rows`, or dispose of them durably if that proves impossible.

        Implementations must not raise for a batch they have dealt with -- a
        dead-lettered batch is handled, not failed. Raising means the rows are
        still the caller's problem, which for the ingester means the flush is
        abandoned and the buffer keeps them.
        """
        ...


class MemorySink:
    """Collects writes in a list. For tests and for wiring work in isolation."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, list[dict]]] = []

    def write(self, record_type: str, rows: list[dict]) -> None:
        # Copied, so a later `Buffer.clear()` cannot empty what was recorded.
        self.writes.append((record_type, list(rows)))
