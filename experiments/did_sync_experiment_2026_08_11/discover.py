"""DID discovery for the two ablations."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any

from atproto import Client

from experimentation.aoc_followers_backfill.constants import FOLLOWERS_PAGE_SIZE, TARGET_HANDLE

PLC_EXPORT_URL = "https://plc.directory/export"
PLC_PAGE_SIZE = 1000  # PLC export max page size


@dataclass
class RateLimitEvent:
    source: str
    at_unix: float
    status_code: int | None
    detail: str
    retry_after: str | None = None


@dataclass
class DiscoveryResult:
    ablation: str
    dids: list[str]
    request_count: int
    runtime_seconds: float
    rate_limit_events: list[RateLimitEvent] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ablation": self.ablation,
            "did_count": len(self.dids),
            "dids": self.dids,
            "request_count": self.request_count,
            "runtime_seconds": self.runtime_seconds,
            "rate_limit_events": [asdict(e) for e in self.rate_limit_events],
            "extra": self.extra,
        }


def _rate_limit_headers(headers: dict[str, str]) -> dict[str, str]:
    interesting = {}
    for key, value in headers.items():
        lower = key.lower()
        if any(token in lower for token in ("rate", "limit", "retry", "remaining")):
            interesting[key] = value
    return interesting


def discover_plc_dids(target: int = 1000) -> DiscoveryResult:
    """Ablation 1: walk PLC directory export from the start until `target` unique DIDs."""
    start = time.perf_counter()
    dids: list[str] = []
    seen: set[str] = set()
    request_count = 0
    rate_limit_events: list[RateLimitEvent] = []
    after: str | None = None
    pages = 0
    last_headers: dict[str, str] = {}

    while len(dids) < target:
        params = f"count={PLC_PAGE_SIZE}"
        if after:
            params += f"&after={urllib.parse.quote(after)}"
        url = f"{PLC_EXPORT_URL}?{params}"
        request_count += 1
        pages += 1
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:
                headers = {k: v for k, v in resp.headers.items()}
                last_headers = _rate_limit_headers(headers)
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            retry_after = e.headers.get("Retry-After") if e.headers else None
            if e.code == 429:
                rate_limit_events.append(
                    RateLimitEvent(
                        source="plc.directory/export",
                        at_unix=time.time(),
                        status_code=429,
                        detail=str(e),
                        retry_after=retry_after,
                    )
                )
                time.sleep(float(retry_after) if retry_after and retry_after.isdigit() else 5)
                continue
            raise

        lines = [ln for ln in body.splitlines() if ln.strip()]
        if not lines:
            break

        last_created_at = None
        for line in lines:
            op = json.loads(line)
            last_created_at = op.get("createdAt")
            did = op.get("did")
            if not did or did in seen:
                continue
            seen.add(did)
            dids.append(did)
            if len(dids) >= target:
                break

        if last_created_at is None or last_created_at == after:
            break
        after = last_created_at

    runtime = time.perf_counter() - start
    return DiscoveryResult(
        ablation="ablation1_plc",
        dids=dids[:target],
        request_count=request_count,
        runtime_seconds=runtime,
        rate_limit_events=rate_limit_events,
        extra={
            "endpoint": PLC_EXPORT_URL,
            "pages": pages,
            "page_size": PLC_PAGE_SIZE,
            "final_after_cursor": after,
            "last_rate_limit_headers": last_headers,
            "note": (
                "PLC export returns NDJSON operations chronologically from genesis. "
                "Multiple ops can share a DID; we collect unique DIDs."
            ),
        },
    )


def discover_aoc_bfs_dids(client: Client, target: int = 1000) -> DiscoveryResult:
    """Ablation 2: BFS over getFollowers starting at AOC until `target` unique DIDs."""
    start = time.perf_counter()
    request_count = 0
    rate_limit_events: list[RateLimitEvent] = []

    profile = client.app.bsky.actor.get_profile({"actor": TARGET_HANDLE})
    request_count += 1
    seed_did = profile.did

    dids: list[str] = []
    seen: set[str] = set()
    # BFS queue of accounts whose followers we will expand.
    queue: deque[str] = deque([seed_did])
    queued: set[str] = {seed_did}
    depth_of = {seed_did: 0}
    max_depth_reached = 0
    pages_by_depth: dict[int, int] = {}

    while queue and len(dids) < target:
        actor = queue.popleft()
        depth = depth_of[actor]
        cursor = None

        while len(dids) < target:
            try:
                response = client.app.bsky.graph.get_followers(
                    {"actor": actor, "limit": FOLLOWERS_PAGE_SIZE, "cursor": cursor}
                )
                request_count += 1
                pages_by_depth[depth] = pages_by_depth.get(depth, 0) + 1
            except Exception as e:
                status = getattr(getattr(e, "response", None), "status_code", None)
                message = str(e)
                is_rate = status == 429 or "429" in message or "ratelimit" in message.lower()
                if is_rate:
                    rate_limit_events.append(
                        RateLimitEvent(
                            source="app.bsky.graph.getFollowers",
                            at_unix=time.time(),
                            status_code=status,
                            detail=message,
                        )
                    )
                    time.sleep(5)
                    continue
                # Skip this actor on hard failure and continue BFS.
                break

            followers = response.followers or []
            if not followers:
                break

            for follower in followers:
                did = follower.did
                if did in seen:
                    continue
                seen.add(did)
                dids.append(did)
                max_depth_reached = max(max_depth_reached, depth + 1)
                # Enqueue for further BFS expansion (followers-of-followers).
                if did not in queued:
                    queued.add(did)
                    queue.append(did)
                    depth_of[did] = depth + 1
                if len(dids) >= target:
                    break

            cursor = response.cursor
            if not cursor:
                break

    runtime = time.perf_counter() - start
    return DiscoveryResult(
        ablation="ablation2_aoc_bfs",
        dids=dids[:target],
        request_count=request_count,
        runtime_seconds=runtime,
        rate_limit_events=rate_limit_events,
        extra={
            "seed_handle": TARGET_HANDLE,
            "seed_did": seed_did,
            "seed_followers_count": profile.followers_count,
            "max_depth_reached": max_depth_reached,
            "pages_by_depth": pages_by_depth,
            "followers_page_size": FOLLOWERS_PAGE_SIZE,
            "note": (
                "BFS over getFollowers: level 0 is AOC, collected DIDs are followers "
                "encountered while expanding the queue. AOC herself is not counted."
            ),
        },
    )
