"""Fetch repos via getRepo and derive profile / validity metrics."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from atproto import CAR, Client
from atproto_core.cid import CID

from experimentation.aoc_followers_backfill.client import create_public_client, create_relay_client

DAYS_BACK = 183  # ~6 months
MIN_FOLLOWERS = 10
MIN_FOLLOWEES = 10
MIN_ORIGINAL_POSTS_6M = 20
MIN_INTERACTIONS_6M = 20

PROFILES_BATCH_SIZE = 25


@dataclass
class ProfileStats:
    did: str
    handle: str | None = None
    followers: int | None = None
    followees: int | None = None
    posts: int | None = None
    account_created_at: str | None = None
    # Repo-derived totals
    repo_posts: int | None = None
    repo_followees: int | None = None
    repo_likes: int | None = None
    repo_reposts: int | None = None
    repo_bookmarks: int | None = None
    # 6-month activity from getRepo
    original_posts_6m: int | None = None
    replies_6m: int | None = None
    quotes_6m: int | None = None
    likes_6m: int | None = None
    reposts_6m: int | None = None
    bookmarks_6m: int | None = None
    interactions_6m: int | None = None
    profile_record_created_at: str | None = None
    getrepo_bytes: int | None = None
    getrepo_seconds: float | None = None
    error: str | None = None
    rate_limited: bool = False
    valid: bool | None = None
    invalid_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_bsky_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _to_cid(value: bytes | CID | None) -> CID | None:
    if value is None:
        return None
    if isinstance(value, CID):
        return value
    return CID.decode(value)


def _is_quote_embed(embed: dict | None) -> bool:
    if not embed:
        return False
    embed_type = embed.get("$type", "")
    return embed_type in {
        "app.bsky.embed.record",
        "app.bsky.embed.recordWithMedia",
    }


def _is_rate_limited(exc: Exception) -> bool:
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if status_code == 429:
        return True
    message = str(exc).lower()
    return "429" in message or "ratelimit" in message


def count_repo_activity(repo_bytes: bytes, cutoff: datetime) -> dict[str, Any]:
    """Walk getRepo CAR/MST and count profile + activity stats without retaining records."""
    car = CAR.from_bytes(repo_bytes)
    commit = car.blocks[car.root]
    blocks = car.blocks

    posts = followees = likes = reposts = bookmarks = 0
    original_posts_6m = replies_6m = quotes_6m = 0
    likes_6m = reposts_6m = bookmarks_6m = 0
    profile_created_at: str | None = None

    def consider(record: dict) -> None:
        nonlocal posts, followees, likes, reposts, bookmarks
        nonlocal original_posts_6m, replies_6m, quotes_6m
        nonlocal likes_6m, reposts_6m, bookmarks_6m, profile_created_at

        collection = record.get("$type")
        if collection == "app.bsky.actor.profile":
            profile_created_at = record.get("createdAt")
            return

        created_at = record.get("createdAt")
        created_dt = _parse_bsky_datetime(created_at) if created_at else None
        in_window = created_dt is not None and created_dt >= cutoff

        if collection == "app.bsky.feed.post":
            posts += 1
            if in_window:
                is_reply = record.get("reply") is not None
                is_quote = _is_quote_embed(record.get("embed"))
                if is_reply:
                    replies_6m += 1
                else:
                    original_posts_6m += 1
                if is_quote:
                    quotes_6m += 1
        elif collection == "app.bsky.graph.follow":
            followees += 1
        elif collection == "app.bsky.feed.like":
            likes += 1
            if in_window:
                likes_6m += 1
        elif collection == "app.bsky.feed.repost":
            reposts += 1
            if in_window:
                reposts_6m += 1
        elif collection in {"app.bsky.bookmark", "app.bsky.bookmark.bookmark"}:
            bookmarks += 1
            if in_window:
                bookmarks_6m += 1

    def walk(node_cid: CID | None, prev_key: str) -> str:
        if node_cid is None:
            return prev_key
        node = blocks[node_cid]
        prev_key = walk(_to_cid(node["l"]), prev_key)
        for entry in node["e"]:
            key_suffix = entry["k"].decode("ascii")
            full_key = prev_key[: entry["p"]] + key_suffix
            value_cid = _to_cid(entry["v"])
            record = blocks.get(value_cid)
            if isinstance(record, dict) and "$type" in record:
                consider(record)
            prev_key = full_key
            prev_key = walk(_to_cid(entry.get("t")), prev_key)
        return prev_key

    walk(_to_cid(commit["data"]), "")

    interactions_6m = likes_6m + bookmarks_6m + quotes_6m + reposts_6m + replies_6m
    return {
        "repo_posts": posts,
        "repo_followees": followees,
        "repo_likes": likes,
        "repo_reposts": reposts,
        "repo_bookmarks": bookmarks,
        "original_posts_6m": original_posts_6m,
        "replies_6m": replies_6m,
        "quotes_6m": quotes_6m,
        "likes_6m": likes_6m,
        "reposts_6m": reposts_6m,
        "bookmarks_6m": bookmarks_6m,
        "interactions_6m": interactions_6m,
        "profile_record_created_at": profile_created_at,
    }


def analyze_did(
    relay_client: Client,
    did: str,
    cutoff: datetime,
    *,
    max_retries: int = 4,
) -> ProfileStats:
    stats = ProfileStats(did=did)
    t0 = time.perf_counter()
    repo_bytes: bytes | None = None
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            repo_bytes = relay_client.com.atproto.sync.get_repo({"did": did})
            last_error = None
            break
        except Exception as e:
            last_error = e
            if _is_rate_limited(e) and attempt < max_retries:
                stats.rate_limited = True
                sleep_s = min(2 ** attempt, 30)
                time.sleep(sleep_s)
                continue
            break

    stats.getrepo_seconds = time.perf_counter() - t0
    if repo_bytes is None:
        stats.error = f"getRepo failed: {last_error}"
        stats.rate_limited = bool(last_error and _is_rate_limited(last_error))
        return stats

    stats.getrepo_bytes = len(repo_bytes)

    try:
        activity = count_repo_activity(repo_bytes, cutoff)
    except Exception as e:
        stats.error = f"CAR/MST decode failed: {e}"
        return stats

    for key, value in activity.items():
        setattr(stats, key, value)

    # Prefer AppView counts when available; fall back to repo-derived.
    stats.posts = stats.repo_posts
    stats.followees = stats.repo_followees
    return stats


def fetch_appview_profiles(public_client: Client, dids: list[str]) -> dict[str, dict[str, Any]]:
    """Batch getProfiles for follower counts / handles / createdAt."""
    out: dict[str, dict[str, Any]] = {}
    for i in range(0, len(dids), PROFILES_BATCH_SIZE):
        batch = dids[i : i + PROFILES_BATCH_SIZE]
        try:
            profiles = public_client.app.bsky.actor.get_profiles({"actors": batch}).profiles
        except Exception:
            # Fall back to one-by-one for partial progress.
            for did in batch:
                try:
                    p = public_client.app.bsky.actor.get_profile({"actor": did})
                    profiles = [p]
                    _ingest_profile(out, p)
                except Exception:
                    continue
            continue
        for p in profiles:
            _ingest_profile(out, p)
    return out


def _ingest_profile(out: dict[str, dict[str, Any]], p: Any) -> None:
    out[p.did] = {
        "handle": p.handle,
        "followers": p.followers_count,
        "followees_appview": p.follows_count,
        "posts_appview": p.posts_count,
        "account_created_at": getattr(p, "created_at", None),
    }


def apply_appview(stats: ProfileStats, appview: dict[str, Any] | None) -> None:
    if not appview:
        return
    stats.handle = appview.get("handle")
    stats.followers = appview.get("followers")
    stats.account_created_at = appview.get("account_created_at") or stats.profile_record_created_at
    # Keep repo-derived posts/followees as primary (from getRepo), but if repo
    # failed, fall back to AppView totals.
    if stats.posts is None:
        stats.posts = appview.get("posts_appview")
    if stats.followees is None:
        stats.followees = appview.get("followees_appview")


def evaluate_validity(stats: ProfileStats) -> None:
    reasons: list[str] = []
    if stats.error:
        stats.valid = False
        stats.invalid_reasons = [stats.error]
        return

    followers = stats.followers or 0
    followees = stats.followees or 0
    original = stats.original_posts_6m or 0
    interactions = stats.interactions_6m or 0

    if followers < MIN_FOLLOWERS:
        reasons.append(f"followers {followers} < {MIN_FOLLOWERS}")
    if followees < MIN_FOLLOWEES:
        reasons.append(f"followees {followees} < {MIN_FOLLOWEES}")
    if original < MIN_ORIGINAL_POSTS_6M:
        reasons.append(f"original_posts_6m {original} < {MIN_ORIGINAL_POSTS_6M}")
    if interactions < MIN_INTERACTIONS_6M:
        reasons.append(f"interactions_6m {interactions} < {MIN_INTERACTIONS_6M}")

    stats.valid = len(reasons) == 0
    stats.invalid_reasons = reasons


def analyze_dids(
    dids: list[str],
    *,
    workers: int = 8,
    progress_every: int = 25,
) -> tuple[list[ProfileStats], dict[str, Any]]:
    """Run getRepo analysis over DIDs concurrently; overlay AppView follower metadata."""
    cutoff = datetime.now(UTC) - timedelta(days=DAYS_BACK)
    public = create_public_client()

    t0 = time.perf_counter()
    appview = fetch_appview_profiles(public, dids)
    appview_seconds = time.perf_counter() - t0

    results: dict[str, ProfileStats] = {}
    rate_limited_count = 0
    error_count = 0
    getrepo_request_count = 0

    def _one(did: str) -> ProfileStats:
        # Each worker gets its own relay client — atproto Client is not thread-safe.
        local_relay = create_relay_client()
        return analyze_did(local_relay, did, cutoff)

    t1 = time.perf_counter()
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_one, did): did for did in dids}
        for fut in as_completed(futures):
            stats = fut.result()
            getrepo_request_count += 1
            apply_appview(stats, appview.get(stats.did))
            evaluate_validity(stats)
            results[stats.did] = stats
            if stats.rate_limited:
                rate_limited_count += 1
            if stats.error:
                error_count += 1
            done += 1
            if done % progress_every == 0 or done == len(dids):
                elapsed = time.perf_counter() - t1
                print(
                    f"  getRepo progress {done}/{len(dids)} "
                    f"({elapsed:.1f}s, errors={error_count}, rate_limited={rate_limited_count})",
                    flush=True,
                )

    ordered = [results[d] for d in dids if d in results]
    meta = {
        "cutoff_iso": cutoff.isoformat(),
        "days_back": DAYS_BACK,
        "workers": workers,
        "appview_seconds": appview_seconds,
        "getrepo_seconds": time.perf_counter() - t1,
        "getrepo_request_count": getrepo_request_count,
        "rate_limited_count": rate_limited_count,
        "error_count": error_count,
        "valid_count": sum(1 for s in ordered if s.valid),
        "did_count": len(ordered),
        "validity_thresholds": {
            "min_followers": MIN_FOLLOWERS,
            "min_followees": MIN_FOLLOWEES,
            "min_original_posts_6m": MIN_ORIGINAL_POSTS_6M,
            "min_interactions_6m": MIN_INTERACTIONS_6M,
            "interactions_definition": "like + save/bookmark + quote + repost + reply in window",
        },
    }
    return ordered, meta
