"""The contract between the buffers and wherever their rows end up."""

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
