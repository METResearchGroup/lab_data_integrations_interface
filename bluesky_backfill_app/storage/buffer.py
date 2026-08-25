import time

from bluesky_backfill_app.constants import MAX_BUFFER_AGE_SECONDS, MAX_BUFFER_DIDS


class DidBuffer:
    """DIDs awaiting a write, deduped within the flush window."""

    def __init__(
        self,
        max_dids: int = MAX_BUFFER_DIDS,
        max_age_seconds: float = MAX_BUFFER_AGE_SECONDS,
    ) -> None:
        self.dids: list[str] = []
        self.seen: set[str] = set()
        self.max_dids = max_dids
        self.max_age_seconds = max_age_seconds
        # monotonic, so an NTP correction cannot fire the timer early.
        self.last_flush = time.monotonic()

    def add(self, did: str) -> None:
        raise NotImplementedError

    def should_flush(self) -> bool:
        raise NotImplementedError

    def flush_reason(self) -> str:
        """Count wins when both thresholds have tripped."""

        raise NotImplementedError

    def clear(self) -> None:
        """Empty the buffer and restart the age timer."""

        raise NotImplementedError
