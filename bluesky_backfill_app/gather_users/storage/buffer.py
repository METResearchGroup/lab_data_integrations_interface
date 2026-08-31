import time

from bluesky_backfill_app.gather_users.constants import (
    FLUSH_REASON_AGE,
    FLUSH_REASON_COUNT,
    MAX_BUFFER_AGE_SECONDS,
    MAX_BUFFER_DIDS,
)


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

    def __len__(self) -> int:
        return len(self.dids)

    def add(self, did: str) -> None:
        if did in self.seen:
            return
        self.seen.add(did)
        self.dids.append(did)

    def should_flush(self) -> bool:
        if not self.dids:
            return False
        return (
            len(self.dids) >= self.max_dids
            or time.monotonic() - self.last_flush >= self.max_age_seconds
        )

    def flush_reason(self) -> str:
        """Count wins when both thresholds have tripped."""

        if not self.should_flush():
            raise ValueError("no flush threshold has been hit")
        if len(self.dids) >= self.max_dids:
            return FLUSH_REASON_COUNT
        return FLUSH_REASON_AGE

    def clear(self) -> None:
        """Empty the buffer and restart the age timer."""

        self.dids = []
        self.seen = set()
        self.last_flush = time.monotonic()
