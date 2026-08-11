"""DID discovery for PLC export and AOC follower breadth first search.

Run from repo root::

    PYTHONPATH=. uv run python -m experiments.did_sync_experiment_2026_08_11.run_experiment
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from atproto import Client

from experiments.did_sync_experiment_2026_08_11.constants import (
    ABLATION1_NAME,
    PLC_EXPORT_URL,
    PLC_MAX_LOOKBACK_HOURS,
    PLC_PAGE_SIZE,
    PLC_RECENT_LOOKBACK_HOURS,
)

UrlOpen = Callable[..., Any]


@dataclass
class RateLimitEvent:
    """One observed rate limit response during discovery."""

    source: str
    at_unix: float
    status_code: int | None
    detail: str
    retry_after: str | None = None


@dataclass
class DiscoveryResult:
    """Unique DIDs plus request, runtime, and rate limit metrics."""

    ablation: str
    dids: list[str]
    request_count: int
    runtime_seconds: float
    rate_limit_events: list[RateLimitEvent] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize discovery metrics for JSON output."""
        return {
            "ablation": self.ablation,
            "did_count": len(self.dids),
            "dids": self.dids,
            "request_count": self.request_count,
            "runtime_seconds": self.runtime_seconds,
            "rate_limit_events": [asdict(event) for event in self.rate_limit_events],
            "extra": self.extra,
        }


def _iso_utc(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _rate_limit_headers(headers: dict[str, str]) -> dict[str, str]:
    interesting: dict[str, str] = {}
    for key, value in headers.items():
        lower = key.lower()
        if any(token in lower for token in ("rate", "limit", "retry", "remaining")):
            interesting[key] = value
    return interesting


def _retry_sleep_seconds(retry_after: str | None) -> float:
    if retry_after is not None and retry_after.isdigit():
        return float(retry_after)
    return 5.0


def _fetch_plc_page(
    after: str,
    urlopen: UrlOpen,
    rate_limit_events: list[RateLimitEvent],
    sleep: Callable[[float], None],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Fetch one PLC export page, retrying once-style on HTTP 429."""
    params = f"count={PLC_PAGE_SIZE}&after={urllib.parse.quote(after)}"
    url = f"{PLC_EXPORT_URL}?{params}"
    while True:
        try:
            with urlopen(url, timeout=120) as resp:
                headers = {k: v for k, v in resp.headers.items()}
                body = resp.read().decode("utf-8")
            lines = [line for line in body.splitlines() if line.strip()]
            ops = [json.loads(line) for line in lines]
            return ops, _rate_limit_headers(headers)
        except urllib.error.HTTPError as exc:
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            if exc.code == 429:
                rate_limit_events.append(
                    RateLimitEvent(
                        source="plc.directory/export",
                        at_unix=time.time(),
                        status_code=429,
                        detail=str(exc),
                        retry_after=retry_after,
                    )
                )
                sleep(_retry_sleep_seconds(retry_after))
                continue
            raise


def discover_plc_dids(
    target: int,
    now: datetime | None = None,
    urlopen: UrlOpen = urllib.request.urlopen,
    sleep: Callable[[float], None] = time.sleep,
) -> DiscoveryResult:
    """Collect unique DIDs from PLC export starting at a recent cursor.

    Starts ``after`` at ``now - PLC_RECENT_LOOKBACK_HOURS``. If that window
    cannot fill ``target``, doubles lookback up to ``PLC_MAX_LOOKBACK_HOURS``.

    Parameters
    ----------
    target
        Number of unique DIDs to collect.
    now
        Optional clock for tests. Defaults to current UTC time.
    urlopen
        HTTP opener used for PLC export pages.
    sleep
        Sleep callable used after HTTP 429 responses.

    Returns
    -------
    DiscoveryResult
        Ordered unique DIDs and discovery metrics.
    """
    start = time.perf_counter()
    clock = now if now is not None else datetime.now(UTC)
    dids: list[str] = []
    seen: set[str] = set()
    request_count = 0
    rate_limit_events: list[RateLimitEvent] = []
    pages = 0
    lookback_hours = PLC_RECENT_LOOKBACK_HOURS
    initial_after = _iso_utc(clock - timedelta(hours=lookback_hours))
    after = initial_after
    final_after = after
    last_headers: dict[str, str] = {}
    exhausted_lookbacks: set[int] = set()

    while len(dids) < target:
        request_count += 1
        pages += 1
        ops, last_headers = _fetch_plc_page(after, urlopen, rate_limit_events, sleep)
        if not ops:
            exhausted_lookbacks.add(lookback_hours)
            if lookback_hours >= PLC_MAX_LOOKBACK_HOURS:
                break
            lookback_hours = min(lookback_hours * 2, PLC_MAX_LOOKBACK_HOURS)
            if lookback_hours in exhausted_lookbacks:
                break
            after = _iso_utc(clock - timedelta(hours=lookback_hours))
            continue

        last_created_at = None
        for op in ops:
            last_created_at = op.get("createdAt") or op.get("seq")
            did = op.get("did")
            if not did or did in seen:
                continue
            seen.add(did)
            dids.append(did)
            if len(dids) >= target:
                break

        if last_created_at is None or str(last_created_at) == after:
            exhausted_lookbacks.add(lookback_hours)
            if lookback_hours >= PLC_MAX_LOOKBACK_HOURS or len(dids) >= target:
                break
            lookback_hours = min(lookback_hours * 2, PLC_MAX_LOOKBACK_HOURS)
            after = _iso_utc(clock - timedelta(hours=lookback_hours))
            continue

        after = str(last_created_at)
        final_after = after

    runtime = time.perf_counter() - start
    extra: dict[str, Any] = {
        "initial_after": initial_after,
        "final_after": final_after,
        "pages": pages,
        "lookback_hours_final": lookback_hours,
        "rate_limit_header_sample": last_headers,
    }
    if len(dids) < target:
        extra["shortfall"] = target - len(dids)

    return DiscoveryResult(
        ablation=ABLATION1_NAME,
        dids=dids,
        request_count=request_count,
        runtime_seconds=runtime,
        rate_limit_events=rate_limit_events,
        extra=extra,
    )


def discover_aoc_bfs_dids(target: int, client: Client | None = None) -> DiscoveryResult:
    """Collect unique DIDs by breadth first search over AOC followers.

    Parameters
    ----------
    target
        Number of unique DIDs to collect.
    client
        Optional AppView client. When omitted, a public client is created.

    Returns
    -------
    DiscoveryResult
        Ordered unique DIDs and discovery metrics.
    """
    raise NotImplementedError("discover_aoc_bfs_dids is implemented in step 3")
