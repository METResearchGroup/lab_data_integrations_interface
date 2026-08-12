"""DID discovery for PLC export, AOC follower BFS, and relay listRepos.

Run from repo root::

    PYTHONPATH=. uv run python -m experiments.did_sync_experiment_2026_08_11.run_experiment
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from atproto import Client

from experimentation.aoc_followers_backfill.client import create_public_client
from experiments.did_sync_experiment_2026_08_11.constants import (
    ABLATION1_NAME,
    ABLATION2_NAME,
    ABLATION3_NAME,
    ABLATION4_NAME,
    AOC_HANDLE,
    FOLLOWERS_PAGE_SIZE,
    LIST_REPOS_PAGE_SIZE,
    LIST_REPOS_URL,
    PLC_EXPORT_URL,
    PLC_MAX_LOOKBACK_HOURS,
    PLC_OLD_LOOKBACK_HOURS,
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


def _append_unique_dids_from_ops(
    ops: list[dict[str, Any]],
    dids: list[str],
    seen: set[str],
    target: int,
) -> str | int | None:
    """Append unseen DIDs from one PLC page. Returns the last createdAt/seq cursor."""
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
    return last_created_at


def _next_plc_lookback(
    lookback_hours: int,
    exhausted_lookbacks: set[int],
    clock: datetime,
    max_lookback_hours: int,
) -> tuple[int, str] | None:
    """Double lookback and return (new_lookback, after), or None when exhausted."""
    exhausted_lookbacks.add(lookback_hours)
    if lookback_hours >= max_lookback_hours:
        return None
    lookback_hours = min(lookback_hours * 2, max_lookback_hours)
    if lookback_hours in exhausted_lookbacks:
        return None
    return lookback_hours, _iso_utc(clock - timedelta(hours=lookback_hours))


@dataclass
class _PlcWalkState:
    dids: list[str]
    seen: set[str]
    after: str
    final_after: str
    lookback_hours: int
    exhausted_lookbacks: set[int]
    pages: int
    request_count: int
    last_headers: dict[str, str]
    expand_lookback: bool = True
    max_lookback_hours: int = PLC_MAX_LOOKBACK_HOURS


def _advance_plc_walk(
    state: _PlcWalkState,
    target: int,
    clock: datetime,
    urlopen: UrlOpen,
    rate_limit_events: list[RateLimitEvent],
    sleep: Callable[[float], None],
) -> bool:
    """Process one PLC page. Returns False when the walk should stop."""
    state.request_count += 1
    state.pages += 1
    ops, state.last_headers = _fetch_plc_page(state.after, urlopen, rate_limit_events, sleep)
    if not ops:
        if not state.expand_lookback:
            return False
        expanded = _next_plc_lookback(
            state.lookback_hours,
            state.exhausted_lookbacks,
            clock,
            state.max_lookback_hours,
        )
        if expanded is None:
            return False
        state.lookback_hours, state.after = expanded
        return True

    last_created_at = _append_unique_dids_from_ops(ops, state.dids, state.seen, target)
    if last_created_at is None or str(last_created_at) == state.after:
        if len(state.dids) >= target:
            return False
        if not state.expand_lookback:
            return False
        expanded = _next_plc_lookback(
            state.lookback_hours,
            state.exhausted_lookbacks,
            clock,
            state.max_lookback_hours,
        )
        if expanded is None:
            return False
        state.lookback_hours, state.after = expanded
        return True

    state.after = str(last_created_at)
    state.final_after = state.after
    return len(state.dids) < target


def discover_plc_dids(
    target: int,
    now: datetime | None = None,
    urlopen: UrlOpen = urllib.request.urlopen,
    sleep: Callable[[float], None] = time.sleep,
    *,
    lookback_hours: int = PLC_RECENT_LOOKBACK_HOURS,
    max_lookback_hours: int = PLC_MAX_LOOKBACK_HOURS,
    expand_lookback: bool = True,
    ablation: str = ABLATION1_NAME,
) -> DiscoveryResult:
    """Collect unique DIDs from PLC export starting at a cursor.

    By default starts ``after`` at ``now - PLC_RECENT_LOOKBACK_HOURS``. If that
    window cannot fill ``target`` and ``expand_lookback`` is true, doubles
    lookback up to ``max_lookback_hours``.

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
    lookback_hours
        Initial hours before ``now`` for the ``after`` cursor.
    max_lookback_hours
        Cap used when expanding lookback after empty or stuck pages.
    expand_lookback
        When false, keep the fixed cursor and only walk forward.
    ablation
        Ablation name written into the discovery artifact.

    Returns
    -------
    DiscoveryResult
        Ordered unique DIDs and discovery metrics.
    """
    start = time.perf_counter()
    clock = now if now is not None else datetime.now(UTC)
    initial_after = _iso_utc(clock - timedelta(hours=lookback_hours))
    rate_limit_events: list[RateLimitEvent] = []
    state = _PlcWalkState(
        dids=[],
        seen=set(),
        after=initial_after,
        final_after=initial_after,
        lookback_hours=lookback_hours,
        exhausted_lookbacks=set(),
        pages=0,
        request_count=0,
        last_headers={},
        expand_lookback=expand_lookback,
        max_lookback_hours=max_lookback_hours,
    )

    while len(state.dids) < target:
        if not _advance_plc_walk(state, target, clock, urlopen, rate_limit_events, sleep):
            break

    runtime = time.perf_counter() - start
    extra: dict[str, Any] = {
        "initial_after": initial_after,
        "final_after": state.final_after,
        "pages": state.pages,
        "lookback_hours_final": state.lookback_hours,
        "lookback_hours_initial": lookback_hours,
        "expand_lookback": expand_lookback,
        "rate_limit_header_sample": state.last_headers,
    }
    if len(state.dids) < target:
        extra["shortfall"] = target - len(state.dids)

    return DiscoveryResult(
        ablation=ablation,
        dids=state.dids,
        request_count=state.request_count,
        runtime_seconds=runtime,
        rate_limit_events=rate_limit_events,
        extra=extra,
    )


def discover_plc_old_dids(
    target: int,
    now: datetime | None = None,
    urlopen: UrlOpen = urllib.request.urlopen,
    sleep: Callable[[float], None] = time.sleep,
) -> DiscoveryResult:
    """Collect unique DIDs from PLC export starting ~6 months ago.

    Uses a fixed older cursor (no lookback expansion) and walks forward until
    ``target`` unique DIDs are collected.
    """
    return discover_plc_dids(
        target,
        now=now,
        urlopen=urlopen,
        sleep=sleep,
        lookback_hours=PLC_OLD_LOOKBACK_HOURS,
        max_lookback_hours=PLC_OLD_LOOKBACK_HOURS,
        expand_lookback=False,
        ablation=ABLATION3_NAME,
    )


def _is_rate_limited_error(exc: Exception) -> bool:
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if status_code == 429:
        return True
    message = str(exc).lower()
    return "429" in message or "ratelimit" in message or "rate limit" in message


def _get_followers_page(
    client: Client,
    actor: str,
    cursor: str | None,
    rate_limit_events: list[RateLimitEvent],
    sleep: Callable[[float], None],
):
    """Fetch one followers page with retry on rate limits."""
    params: dict[str, Any] = {"actor": actor, "limit": FOLLOWERS_PAGE_SIZE}
    if cursor:
        params["cursor"] = cursor
    while True:
        try:
            return client.app.bsky.graph.get_followers(params)
        except Exception as exc:
            if not _is_rate_limited_error(exc):
                raise
            rate_limit_events.append(
                RateLimitEvent(
                    source="app.bsky.graph.getFollowers",
                    at_unix=time.time(),
                    status_code=429,
                    detail=str(exc),
                    retry_after=None,
                )
            )
            sleep(5.0)


def _ingest_follower_page(
    followers: list[Any],
    seed_did: str,
    dids: list[str],
    seen: set[str],
    queue: deque[tuple[str, int]],
    enqueued: set[str],
    depth: int,
    target: int,
) -> None:
    """Add unseen followers to the result list and BFS queue."""
    for follower in followers:
        follower_did = follower.did
        if follower_did in seen or follower_did == seed_did:
            continue
        seen.add(follower_did)
        dids.append(follower_did)
        if follower_did not in enqueued:
            queue.append((follower_did, depth + 1))
            enqueued.add(follower_did)
        if len(dids) >= target:
            break


def _expand_followers_for_did(
    appview: Client,
    expand_did: str,
    depth: int,
    target: int,
    seed_did: str,
    dids: list[str],
    seen: set[str],
    queue: deque[tuple[str, int]],
    enqueued: set[str],
    pages_by_depth: dict[int, int],
    rate_limit_events: list[RateLimitEvent],
    sleep: Callable[[float], None],
) -> int:
    """Page followers for one DID. Returns the number of follower page requests."""
    request_count = 0
    cursor: str | None = None
    while len(dids) < target:
        request_count += 1
        pages_by_depth[depth] = pages_by_depth.get(depth, 0) + 1
        response = _get_followers_page(appview, expand_did, cursor, rate_limit_events, sleep)
        followers = list(response.followers or [])
        if not followers:
            break
        _ingest_follower_page(followers, seed_did, dids, seen, queue, enqueued, depth, target)
        cursor = getattr(response, "cursor", None)
        if not cursor or len(dids) >= target:
            break
    return request_count


def discover_aoc_bfs_dids(
    target: int,
    client: Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> DiscoveryResult:
    """Collect unique DIDs by breadth first search over AOC followers.

    Stops as soon as ``target`` unique follower DIDs are collected. The seed
    account itself is not included in the result list.

    Parameters
    ----------
    target
        Number of unique DIDs to collect.
    client
        Optional AppView client. When omitted, a public client is created.
    sleep
        Sleep callable used after rate limit errors.

    Returns
    -------
    DiscoveryResult
        Ordered unique DIDs and discovery metrics.
    """
    start = time.perf_counter()
    appview = client if client is not None else create_public_client()
    rate_limit_events: list[RateLimitEvent] = []
    request_count = 0

    seed_profile = appview.app.bsky.actor.get_profile({"actor": AOC_HANDLE})
    request_count += 1
    seed_did = seed_profile.did
    seed_followers_count = getattr(seed_profile, "followers_count", None)

    dids: list[str] = []
    seen: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(seed_did, 0)])
    enqueued: set[str] = {seed_did}
    pages_by_depth: dict[int, int] = {}
    max_depth_reached = 0

    while len(dids) < target and queue:
        expand_did, depth = queue.popleft()
        max_depth_reached = max(max_depth_reached, depth)
        request_count += _expand_followers_for_did(
            appview,
            expand_did,
            depth,
            target,
            seed_did,
            dids,
            seen,
            queue,
            enqueued,
            pages_by_depth,
            rate_limit_events,
            sleep,
        )

    runtime = time.perf_counter() - start
    extra: dict[str, Any] = {
        "seed_handle": AOC_HANDLE,
        "seed_did": seed_did,
        "seed_followers_count": seed_followers_count,
        "max_depth_reached": max_depth_reached,
        "pages_by_depth": {str(k): v for k, v in sorted(pages_by_depth.items())},
    }
    if len(dids) < target:
        extra["shortfall"] = target - len(dids)

    return DiscoveryResult(
        ablation=ABLATION2_NAME,
        dids=dids,
        request_count=request_count,
        runtime_seconds=runtime,
        rate_limit_events=rate_limit_events,
        extra=extra,
    )


def _fetch_list_repos_page(
    cursor: str | None,
    urlopen: UrlOpen,
    rate_limit_events: list[RateLimitEvent],
    sleep: Callable[[float], None],
) -> tuple[list[dict[str, Any]], str | None, dict[str, str]]:
    """Fetch one relay listRepos page, retrying on HTTP 429."""
    params = f"limit={LIST_REPOS_PAGE_SIZE}"
    if cursor:
        params = f"{params}&cursor={urllib.parse.quote(cursor)}"
    url = f"{LIST_REPOS_URL}?{params}"
    while True:
        try:
            with urlopen(url, timeout=120) as resp:
                headers = {k: v for k, v in resp.headers.items()}
                payload = json.loads(resp.read().decode("utf-8"))
            repos = payload.get("repos") or []
            if not isinstance(repos, list):
                repos = []
            next_cursor = payload.get("cursor")
            next_cursor_str = next_cursor if isinstance(next_cursor, str) else None
            return repos, next_cursor_str, _rate_limit_headers(headers)
        except urllib.error.HTTPError as exc:
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            if exc.code == 429:
                rate_limit_events.append(
                    RateLimitEvent(
                        source="com.atproto.sync.listRepos",
                        at_unix=time.time(),
                        status_code=429,
                        detail=str(exc),
                        retry_after=retry_after,
                    )
                )
                sleep(_retry_sleep_seconds(retry_after))
                continue
            raise


def discover_list_repos_dids(
    target: int,
    urlopen: UrlOpen = urllib.request.urlopen,
    sleep: Callable[[float], None] = time.sleep,
) -> DiscoveryResult:
    """Collect unique DIDs from relay ``com.atproto.sync.listRepos``.

    Starts at the beginning of the relay enumeration (no cursor) and pages
    forward until ``target`` unique DIDs are collected. This is the relay's
    hosted-repo listing, not a PLC chronology sample.

    Parameters
    ----------
    target
        Number of unique DIDs to collect.
    urlopen
        HTTP opener used for listRepos pages.
    sleep
        Sleep callable used after HTTP 429 responses.

    Returns
    -------
    DiscoveryResult
        Ordered unique DIDs and discovery metrics.
    """
    start = time.perf_counter()
    rate_limit_events: list[RateLimitEvent] = []
    dids: list[str] = []
    seen: set[str] = set()
    cursor: str | None = None
    request_count = 0
    pages = 0
    inactive_count = 0
    status_counts: dict[str, int] = {}
    last_headers: dict[str, str] = {}

    while len(dids) < target:
        request_count += 1
        pages += 1
        repos, next_cursor, last_headers = _fetch_list_repos_page(
            cursor, urlopen, rate_limit_events, sleep
        )
        if not repos:
            break
        for repo in repos:
            if not isinstance(repo, dict):
                continue
            did = repo.get("did")
            if not did or did in seen:
                continue
            if repo.get("active") is False:
                inactive_count += 1
            status = repo.get("status")
            if isinstance(status, str) and status:
                status_counts[status] = status_counts.get(status, 0) + 1
            seen.add(did)
            dids.append(did)
            if len(dids) >= target:
                break
        if len(dids) >= target:
            break
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor

    runtime = time.perf_counter() - start
    extra: dict[str, Any] = {
        "source": LIST_REPOS_URL,
        "pages": pages,
        "final_cursor": cursor,
        "inactive_listed_count": inactive_count,
        "status_counts": status_counts,
        "rate_limit_header_sample": last_headers,
    }
    if len(dids) < target:
        extra["shortfall"] = target - len(dids)

    return DiscoveryResult(
        ablation=ABLATION4_NAME,
        dids=dids,
        request_count=request_count,
        runtime_seconds=runtime,
        rate_limit_events=rate_limit_events,
        extra=extra,
    )
