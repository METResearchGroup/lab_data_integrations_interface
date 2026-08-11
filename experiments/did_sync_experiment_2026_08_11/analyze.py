"""Enrich discovered DIDs via getRepo and classify validity.

Run from repo root::

    PYTHONPATH=. uv run python -m experiments.did_sync_experiment_2026_08_11.run_experiment
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from atproto import Client

from experimentation.aoc_followers_backfill.client import (
    create_public_client,
    create_relay_client,
)
from experimentation.aoc_followers_backfill.mst import decode_repo
from experiments.did_sync_experiment_2026_08_11.constants import (
    DAYS_BACK,
    GETREPO_BASE_BACKOFF_SECONDS,
    GETREPO_MAX_ATTEMPTS,
    GETREPO_MAX_BACKOFF_SECONDS,
    GETREPO_MIN_INTERVAL_SECONDS,
    GETREPO_RATE_LIMIT_COOLDOWN_SECONDS,
    MIN_FOLLOWEES,
    MIN_FOLLOWERS,
    MIN_INTERACTIONS_6M,
    MIN_ORIGINAL_POSTS_6M,
    PROFILES_BATCH_SIZE,
)

QUOTE_EMBED_TYPES = {
    "app.bsky.embed.record",
    "app.bsky.embed.recordWithMedia",
}
BOOKMARK_TYPES = {
    "app.bsky.bookmark",
    "app.bsky.bookmark.bookmark",
}


@dataclass
class ProfileStats:
    """Per-DID profile and six month activity metrics."""

    did: str
    handle: str | None = None
    followers: int | None = None
    followees: int | None = None
    posts: int | None = None
    account_created_at: str | None = None
    original_posts_6m: int | None = None
    interactions_6m: int | None = None
    likes_6m: int | None = None
    reposts_6m: int | None = None
    replies_6m: int | None = None
    quotes_6m: int | None = None
    bookmarks_6m: int | None = None
    valid: bool | None = None
    invalid_reasons: list[str] = field(default_factory=list)
    error: str | None = None
    rate_limited: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize profile metrics for JSONL output."""
        return asdict(self)


@dataclass
class AnalyzeMeta:
    """Aggregate getRepo and AppView metrics for one ablation."""

    getrepo_request_count: int
    getrepo_error_count: int
    getrepo_rate_limit_event_count: int
    getrepo_runtime_seconds: float
    appview_profile_request_count: int
    getrepo_error_breakdown: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize analysis metrics for summary JSON."""
        return asdict(self)


def classify_getrepo_error(error: str | None) -> str | None:
    """Bucket a getRepo failure string for rollup reporting."""
    if not error:
        return None
    lowered = error.lower()
    if "reponotfound" in lowered or "repo not found" in lowered:
        return "repo_not_found"
    if "repotakendown" in lowered or "takendown" in lowered:
        return "repo_takendown"
    if "repodeactivated" in lowered or "deactivated" in lowered:
        return "repo_deactivated"
    if "429" in lowered or "ratelimitexceeded" in lowered or "rate limit exceeded" in lowered:
        return "rate_limit"
    if "network" in lowered or "requestexception" in lowered or "timeout" in lowered:
        return "network"
    if "decode" in lowered:
        return "decode"
    return "other"


@dataclass
class ActivityCounts:
    """Lifetime and windowed activity counts from decoded repo records."""

    followees: int = 0
    posts: int = 0
    original_posts_6m: int = 0
    replies_6m: int = 0
    quotes_6m: int = 0
    likes_6m: int = 0
    reposts_6m: int = 0
    bookmarks_6m: int = 0
    profile_created_at: str | None = None
    earliest_created_at: str | None = None

    @property
    def interactions_6m(self) -> int:
        return (
            self.likes_6m + self.reposts_6m + self.replies_6m + self.quotes_6m + self.bookmarks_6m
        )


def _parse_bsky_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _is_quote_embed(embed: dict | None) -> bool:
    if not embed:
        return False
    return embed.get("$type", "") in QUOTE_EMBED_TYPES


def _exception_status_code(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code is not None:
        return int(status_code)
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        return int(status_code)
    return None


def _xrpc_error_name(exc: Exception) -> str | None:
    """Return the XRPC error name from an atproto response, when present."""
    response = getattr(exc, "response", None)
    content = getattr(response, "content", None)
    error = getattr(content, "error", None)
    if isinstance(error, str) and error.strip():
        return error.strip()
    return None


def _format_exception(exc: Exception) -> str:
    status_code = _exception_status_code(exc)
    xrpc_error = _xrpc_error_name(exc)
    if xrpc_error is not None:
        response = getattr(exc, "response", None)
        content = getattr(response, "content", None)
        detail = getattr(content, "message", None) or xrpc_error
        message = f"{xrpc_error}: {detail}"
    else:
        message = str(exc).strip() or type(exc).__name__
    if status_code is None:
        return message
    return f"{message} (status={status_code})"


def _is_rate_limited(exc: Exception) -> bool:
    """Detect true relay 429 / RateLimitExceeded without matching RateLimit headers.

    atproto stringifies the whole Response, including ``ratelimit-*`` headers on
    ordinary 400 errors. Matching the substring ``ratelimit`` there falsely
    triggers multi-minute cooldowns and contaminates rate-limit metrics.
    """
    status_code = _exception_status_code(exc)
    if status_code == 429:
        return True
    xrpc_error = (_xrpc_error_name(exc) or "").lower()
    if xrpc_error in {"ratelimitexceeded", "rate_limit_exceeded"}:
        return True
    type_name = type(exc).__name__.lower()
    if "ratelimit" in type_name:
        return True
    # Prefer short messages without header dumps; still catch bare SDK strings.
    message = str(exc).strip().lower()
    if len(message) <= 80 and (
        "ratelimitexceeded" in message or message in {"429", "rate limit exceeded"}
    ):
        return True
    return False


def _is_retryable_getrepo_error(exc: Exception) -> bool:
    if _is_rate_limited(exc):
        return True
    # Permanent account/repo outcomes must not burn retry budget.
    xrpc_error = (_xrpc_error_name(exc) or "").lower()
    if xrpc_error in {
        "reponotfound",
        "repotakendown",
        "repodeactivated",
        "reposuspended",
        "accountnotfound",
        "invalidrequest",
    }:
        return False
    status_code = _exception_status_code(exc)
    if status_code in {400, 401, 403, 404}:
        return False
    if status_code in {500, 502, 503, 504}:
        return True
    type_name = type(exc).__name__.lower()
    if "network" in type_name:
        return True
    message = str(exc).lower()
    return any(
        token in message
        for token in ("timeout", "temporarily", "connection reset", "broken pipe", "network")
    )


class RelayRequestPacer:
    """Space and serialize relay getRepo calls on one shared client."""

    def __init__(self, min_interval_seconds: float):
        self._min_interval_seconds = min_interval_seconds
        self._lock = threading.Lock()
        self._next_allowed_at = 0.0

    def call(
        self,
        fn: Callable[[], bytes],
        sleep: Callable[[float], None] = time.sleep,
    ) -> bytes:
        """Run ``fn`` after waiting for the next slot. Only one call runs at a time."""
        with self._lock:
            now = time.monotonic()
            wait_for = max(0.0, self._next_allowed_at - now)
            if wait_for > 0:
                sleep(wait_for)
            try:
                return fn()
            finally:
                self._next_allowed_at = time.monotonic() + self._min_interval_seconds

    def note_rate_limit(self) -> None:
        """Delay the shared relay schedule after a 429 so the budget can recover."""
        with self._lock:
            now = time.monotonic()
            self._next_allowed_at = max(
                self._next_allowed_at,
                now + GETREPO_RATE_LIMIT_COOLDOWN_SECONDS,
            )
            self._min_interval_seconds = max(self._min_interval_seconds, 0.35)


def _track_earliest(current: str | None, candidate: str | None) -> str | None:
    if candidate is None:
        return current
    if current is None:
        return candidate
    current_dt = _parse_bsky_datetime(current)
    candidate_dt = _parse_bsky_datetime(candidate)
    if current_dt is None:
        return candidate
    if candidate_dt is None:
        return current
    return candidate if candidate_dt < current_dt else current


def _count_post_activity(counts: ActivityCounts, record: dict, in_window: bool) -> None:
    counts.posts += 1
    if not in_window:
        return
    is_reply = record.get("reply") is not None
    if is_reply:
        counts.replies_6m += 1
    else:
        counts.original_posts_6m += 1
    if _is_quote_embed(record.get("embed")):
        counts.quotes_6m += 1


def _apply_record_to_counts(counts: ActivityCounts, record: dict, cutoff: datetime) -> None:
    collection = record.get("$type")
    created_at = record.get("createdAt")
    counts.earliest_created_at = _track_earliest(counts.earliest_created_at, created_at)
    created_dt = _parse_bsky_datetime(created_at) if created_at else None
    in_window = created_dt is not None and created_dt >= cutoff

    if collection == "app.bsky.actor.profile":
        counts.profile_created_at = created_at
        return
    if collection == "app.bsky.feed.post":
        _count_post_activity(counts, record, in_window)
        return
    if collection == "app.bsky.graph.follow":
        counts.followees += 1
        return
    if not in_window:
        return
    if collection == "app.bsky.feed.like":
        counts.likes_6m += 1
    elif collection == "app.bsky.feed.repost":
        counts.reposts_6m += 1
    elif collection in BOOKMARK_TYPES:
        counts.bookmarks_6m += 1


def count_activity_from_records(
    records: dict[str, dict],
    cutoff: datetime,
) -> ActivityCounts:
    """Count lifetime and six month activity from decoded repo records.

    Parameters
    ----------
    records
        Map of at-URI to record dicts from ``decode_repo``.
    cutoff
        Inclusive lower bound for the six month activity window.

    Returns
    -------
    ActivityCounts
        Lifetime followee/post totals and windowed interaction parts.
    """
    counts = ActivityCounts()
    for record in records.values():
        _apply_record_to_counts(counts, record, cutoff)
    return counts


def apply_validity(stats: ProfileStats) -> ProfileStats:
    """Mark validity and reasons from follower/followee/activity thresholds.

    Parameters
    ----------
    stats
        Profile row with counts already populated.

    Returns
    -------
    ProfileStats
        The same object with ``valid`` and ``invalid_reasons`` updated.
    """
    reasons: list[str] = []
    followers = stats.followers or 0
    followees = stats.followees or 0
    original_posts = stats.original_posts_6m or 0
    interactions = stats.interactions_6m or 0

    if followers < MIN_FOLLOWERS:
        reasons.append(f"followers<{MIN_FOLLOWERS}")
    if followees < MIN_FOLLOWEES:
        reasons.append(f"followees<{MIN_FOLLOWEES}")
    if original_posts < MIN_ORIGINAL_POSTS_6M:
        reasons.append(f"original_posts_6m<{MIN_ORIGINAL_POSTS_6M}")
    if interactions < MIN_INTERACTIONS_6M:
        reasons.append(f"interactions_6m<{MIN_INTERACTIONS_6M}")

    stats.invalid_reasons = reasons
    stats.valid = len(reasons) == 0 and stats.error is None
    return stats


def _activity_to_stats(did: str, activity: ActivityCounts) -> ProfileStats:
    return ProfileStats(
        did=did,
        followees=activity.followees,
        posts=activity.posts,
        original_posts_6m=activity.original_posts_6m,
        interactions_6m=activity.interactions_6m,
        likes_6m=activity.likes_6m,
        reposts_6m=activity.reposts_6m,
        replies_6m=activity.replies_6m,
        quotes_6m=activity.quotes_6m,
        bookmarks_6m=activity.bookmarks_6m,
        account_created_at=activity.profile_created_at or activity.earliest_created_at,
    )


def _fetch_repo_bytes(
    did: str,
    relay_client: Client,
    pacer: RelayRequestPacer,
    sleep: Callable[[float], None],
) -> tuple[bytes | None, str | None, bool]:
    """Fetch one repo with pacing and retries.

    Returns
    -------
    tuple[bytes | None, str | None, bool]
        Repo bytes (or None), error string (or None), and whether any attempt
        was rate limited.
    """
    last_error: Exception | None = None
    rate_limited = False
    for attempt in range(GETREPO_MAX_ATTEMPTS):
        try:
            repo_bytes = pacer.call(
                lambda: relay_client.com.atproto.sync.get_repo({"did": did}),
                sleep,
            )
            return repo_bytes, None, rate_limited
        except Exception as exc:
            last_error = exc
            if _is_rate_limited(exc):
                rate_limited = True
                pacer.note_rate_limit()
            if not _is_retryable_getrepo_error(exc) or attempt + 1 >= GETREPO_MAX_ATTEMPTS:
                break
            backoff = min(
                GETREPO_MAX_BACKOFF_SECONDS,
                GETREPO_BASE_BACKOFF_SECONDS * (2**attempt),
            )
            sleep(backoff)
    return None, _format_exception(last_error) if last_error else "unknown error", rate_limited


def _analyze_one_did(
    did: str,
    relay_client: Client,
    cutoff: datetime,
    pacer: RelayRequestPacer,
    sleep: Callable[[float], None] = time.sleep,
) -> ProfileStats:
    repo_bytes, fetch_error, rate_limited = _fetch_repo_bytes(did, relay_client, pacer, sleep)
    if repo_bytes is None:
        return ProfileStats(
            did=did,
            error=f"getRepo failed: {fetch_error}",
            valid=False,
            rate_limited=rate_limited,
            invalid_reasons=["getrepo_error"],
        )

    try:
        _, records = decode_repo(repo_bytes)
    except Exception as exc:
        return ProfileStats(
            did=did,
            error=f"CAR/MST decode failed: {_format_exception(exc)}",
            valid=False,
            invalid_reasons=["decode_error"],
        )

    activity = count_activity_from_records(records, cutoff)
    stats = _activity_to_stats(did, activity)
    stats.rate_limited = rate_limited
    return stats


def _batched(items: list[str], batch_size: int) -> list[list[str]]:
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


def _overlay_appview_profiles(
    rows: list[ProfileStats],
    public_client: Client,
) -> int:
    """Overlay AppView handle, followers, and created date onto rows."""
    by_did = {row.did: row for row in rows}
    request_count = 0
    for batch in _batched(list(by_did.keys()), PROFILES_BATCH_SIZE):
        request_count += 1
        try:
            profiles = public_client.app.bsky.actor.get_profiles({"actors": batch}).profiles
        except Exception:
            continue
        for profile in profiles:
            row = by_did.get(profile.did)
            if row is None:
                continue
            row.handle = profile.handle
            row.followers = profile.followers_count
            appview_created = getattr(profile, "created_at", None) or getattr(
                profile, "indexed_at", None
            )
            if appview_created:
                row.account_created_at = appview_created
    return request_count


def analyze_dids(
    dids: list[str],
    workers: int,
    relay_client: Client | None = None,
    public_client: Client | None = None,
    now: datetime | None = None,
) -> tuple[list[ProfileStats], AnalyzeMeta]:
    """Fetch repos for DIDs and classify validity.

    Parameters
    ----------
    dids
        Unique account IDs to enrich.
    workers
        Retained for CLI compatibility. getRepo enrichment runs sequentially
        under a shared paced client to avoid rate-limit skew and session races.
    relay_client
        Optional relay client for getRepo. Created when omitted.
    public_client
        Optional AppView client for profiles. Created when omitted.
    now
        Optional clock for the six month cutoff.

    Returns
    -------
    tuple[list[ProfileStats], AnalyzeMeta]
        Per-DID rows and aggregate analysis metrics.
    """
    clock = now if now is not None else datetime.now(UTC)
    cutoff = clock - timedelta(days=DAYS_BACK)
    relay = relay_client if relay_client is not None else create_relay_client()
    public = public_client if public_client is not None else create_public_client()

    start = time.perf_counter()
    rows_by_did: dict[str, ProfileStats] = {}
    error_count = 0
    rate_limit_count = 0
    error_breakdown: dict[str, int] = {}
    pacer = RelayRequestPacer(GETREPO_MIN_INTERVAL_SECONDS)

    # getRepo uses one shared client; run sequentially so session use stays safe
    # under pacing. ``workers`` is retained for CLI compatibility.
    _ = workers
    for index, did in enumerate(dids, start=1):
        row = _analyze_one_did(did, relay, cutoff, pacer)
        rows_by_did[did] = row
        if row.error:
            error_count += 1
            bucket = classify_getrepo_error(row.error) or "other"
            error_breakdown[bucket] = error_breakdown.get(bucket, 0) + 1
        if row.rate_limited:
            rate_limit_count += 1
        if index % 5 == 0 or index == len(dids):
            print(
                f"getRepo progress {index}/{len(dids)} "
                f"(errors={error_count}, rate_limited={rate_limit_count}, "
                f"breakdown={error_breakdown})",
                flush=True,
            )

    ordered = [rows_by_did[did] for did in dids if did in rows_by_did]
    appview_requests = _overlay_appview_profiles(ordered, public)
    for row in ordered:
        if row.error is None:
            apply_validity(row)

    meta = AnalyzeMeta(
        getrepo_request_count=len(dids),
        getrepo_error_count=error_count,
        getrepo_rate_limit_event_count=rate_limit_count,
        getrepo_runtime_seconds=time.perf_counter() - start,
        appview_profile_request_count=appview_requests,
        getrepo_error_breakdown=error_breakdown,
    )
    return ordered, meta
