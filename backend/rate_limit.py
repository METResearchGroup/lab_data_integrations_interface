"""Caps each user at one accepted query per interval."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable

from fastapi import HTTPException, status

QUERY_INTERVAL_SECONDS = 60


class QueryRateLimiter:
    def __init__(
        self,
        interval: float = QUERY_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._interval = interval
        self._clock = clock
        self._last_accepted: dict[str, float] = {}
        self._lock = threading.Lock()

    def check(self, email: str) -> None:
        with self._lock:
            now = self._clock()
            last = self._last_accepted.get(email)
            if last is not None and now - last < self._interval:
                retry_after = math.ceil(self._interval - (now - last))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many queries. Try again in {retry_after}s.",
                    headers={"Retry-After": str(retry_after)},
                )
            self._last_accepted[email] = now
