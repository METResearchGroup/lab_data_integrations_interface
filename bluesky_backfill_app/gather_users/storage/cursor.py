import logging

logger = logging.getLogger(__name__)


class CursorTracker:
    """Holds the resume cursor, advancing it only once the DIDs are written."""

    def __init__(self, cursor_store) -> None:
        self.cursor_store = cursor_store
        self.cursor_value, self.discovered_count = cursor_store.read()
        self.most_recent_cursor = self.cursor_value

    def observe(self, page_cursor: str | None) -> None:
        if page_cursor is not None:
            self.most_recent_cursor = page_cursor

    def mark_flushed(self, created_count: int) -> None:
        """Persist cursor and count. Logs on failure rather than raising."""

        if self.most_recent_cursor is None:
            return
        if self.most_recent_cursor == self.cursor_value and created_count == 0:
            return

        try:
            self.cursor_store.write(self.most_recent_cursor, created_count)
        except Exception:
            logger.warning("cursor write failed at %s", self.most_recent_cursor, exc_info=True)
            return

        self.cursor_value = self.most_recent_cursor
        self.discovered_count += created_count

    def resume_from(self) -> str | None:
        """None starts at the beginning."""

        return self.cursor_value

    def target_reached(self, target: int, pending: int = 0) -> bool:
        """`pending` counts DIDs buffered but not yet written."""

        return self.discovered_count + pending >= target
