import logging

logger = logging.getLogger(__name__)


class CursorTracker:
    """Holds the resume cursor, advancing it only once the DIDs are written."""

    def __init__(self, cursor_store) -> None:
        self.cursor_store = cursor_store
        self.cursor_value = cursor_store.read()
        self.most_recent_cursor = self.cursor_value

    def observe(self, page_cursor: str | None) -> None:
        if page_cursor is not None:
            self.most_recent_cursor = page_cursor

    def mark_flushed(self) -> None:
        """Persist the cursor. Logs on failure rather than raising."""

        if self.most_recent_cursor is None or self.most_recent_cursor == self.cursor_value:
            return

        try:
            self.cursor_store.write(self.most_recent_cursor)
        except Exception:
            logger.warning("cursor write failed at %s", self.most_recent_cursor, exc_info=True)
            return

        self.cursor_value = self.most_recent_cursor

    def resume_from(self) -> str | None:
        """None starts at the beginning."""

        return self.cursor_value
