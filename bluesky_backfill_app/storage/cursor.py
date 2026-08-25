import logging

logger = logging.getLogger(__name__)


class CursorTracker:
    """Holds the resume cursor, advancing it only once the DIDs are written."""

    def __init__(self, cursor_store) -> None:
        self.cursor_store = cursor_store
        self.cursor_value, self.discovered_count = cursor_store.read()
        self.most_recent_cursor = self.cursor_value

    def observe(self, page_cursor: str | None) -> None:
        raise NotImplementedError

    def mark_flushed(self, created_count: int) -> None:
        """Persist cursor and count. Logs on failure rather than raising."""

        raise NotImplementedError

    def resume_from(self) -> str | None:
        """None starts at the beginning."""

        raise NotImplementedError

    def target_reached(self, target: int) -> bool:
        raise NotImplementedError
