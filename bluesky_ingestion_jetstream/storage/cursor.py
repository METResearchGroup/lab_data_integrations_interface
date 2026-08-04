"""Tracks how far the stream can safely be resumed from."""

import logging
from typing import Protocol

from bluesky_ingestion_jetstream.constants import CURSOR_REWIND_MICROSECONDS

logger = logging.getLogger(__name__)


class CursorStore(Protocol):
    """Durable home for the resume cursor."""

    def read(self) -> int | None:
        """Return the stored cursor, or None if nothing has been stored yet."""
        ...

    def write(self, time_us: int) -> None:
        """Persist `time_us` as the resume cursor."""
        ...


class CursorTracker:
    """Holds the resume cursor, advancing it only once the buffers have flushed."""

    def __init__(self, store: CursorStore) -> None:
        self.store = store
        self.committed = store.read()
        self.pending = self.committed

    def observe(self, time_us: int) -> None:
        """Record an event as seen, whether or not we store it.

        A high water mark rather than an assignment, because a reconnect replays
        events we have already accounted for.
        """

        self.pending = time_us if self.pending is None else max(self.pending, time_us)

    def mark_flushed(self) -> None:
        """Persist the cursor now that everything seen is written."""

        if self.pending is None or self.pending == self.committed:
            return

        try:
            self.store.write(self.pending)
        except Exception:
            # Costs a longer replay on restart, nothing more, and the next flush
            # writes a newer cursor that supersedes this one.
            logger.warning("cursor write failed at %d", self.pending, exc_info=True)
            return

        self.committed = self.pending

    def resume_from(self) -> int | None:
        """Cursor to reconnect with, rewound so a boundary event is replayed, not skipped."""

        if self.committed is None:
            return None
        return max(0, self.committed - CURSOR_REWIND_MICROSECONDS)
