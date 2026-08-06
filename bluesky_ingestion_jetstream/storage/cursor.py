"""Tracks how far the stream can safely be resumed from."""

import logging

from bluesky_ingestion_jetstream.constants import CURSOR_REWIND_MICROSECONDS

logger = logging.getLogger(__name__)


class CursorTracker:
    """Holds the resume cursor, advancing it only once the buffers have flushed."""

    def __init__(self, cursor_store) -> None:
        self.cursor_store = cursor_store
        self.cursor_value = cursor_store.read()
        self.most_recent_event_timestamp = self.cursor_value

    def observe(self, jetstream_event_timestamp: int) -> None:
        """Take the highest timestamp of seen events."""

        if self.most_recent_event_timestamp is None:
            self.most_recent_event_timestamp = jetstream_event_timestamp
        else:
            self.most_recent_event_timestamp = max(
                self.most_recent_event_timestamp, jetstream_event_timestamp
            )

    def mark_flushed(self) -> None:
        """Persist the cursor after all buffers are flushed."""

        if (
            self.most_recent_event_timestamp is None
            or self.most_recent_event_timestamp == self.cursor_value
        ):
            return

        try:
            self.cursor_store.write(self.most_recent_event_timestamp)
        except Exception:
            logger.warning(
                "cursor write failed at %d", self.most_recent_event_timestamp, exc_info=True
            )
            return

        self.cursor_value = self.most_recent_event_timestamp

    def resume_from(self) -> int | None:
        """Cursor to reconnect with, rewound by CURSOR_REWIND_MICROSECONDS to avoid skips.

        Reads the observed position, not the persisted one. A reconnect happens
        inside `stream_events`, below the buffers, so rows seen since the last
        flush are still in memory and still get written -- replaying them would
        only duplicate them. A *restart* is what needs the persisted cursor, and
        `__init__` seeds this from it, so that path is unchanged.

        Only correct while a reconnect leaves the buffers intact. Rebuilding the
        BufferSet per connection would turn this into silent data loss.
        """

        if self.most_recent_event_timestamp is None:
            return None
        return max(0, self.most_recent_event_timestamp - CURSOR_REWIND_MICROSECONDS)
