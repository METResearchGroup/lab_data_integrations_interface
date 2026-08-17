from datetime import UTC, datetime, timedelta

from atproto import Client

from bluesky_ingestion_jetstream.constants import REQUIRED_KEYS
from bluesky_ingestion_jetstream.event_parsing.follows import parse_follow
from bluesky_ingestion_jetstream.event_parsing.likes_and_reposts import parse_like_or_repost
from bluesky_ingestion_jetstream.event_parsing.posts import parse_post
from bluesky_ingestion_jetstream.event_parsing.shared import (
    is_created_at_valid,
    parse_created_at,
    validate_non_null_fields,
)
from experiments.backfill_shape_2026_08_13.constants import DAYS_BACK, TARGET_COLLECTIONS
from experiments.backfill_shape_2026_08_13.mst import decode_repo

_RECORD_PARSERS = {
    "app.bsky.feed.post": parse_post,
    "app.bsky.feed.like": parse_like_or_repost,
    "app.bsky.feed.repost": parse_like_or_repost,
    "app.bsky.graph.follow": parse_follow,
}


def _empty_buckets() -> dict[str, list[dict]]:
    return {name: [] for name in set(TARGET_COLLECTIONS.values())}


def backfill_user(
    user: dict, relay_client: Client, days_back: int = DAYS_BACK
) -> tuple[dict[str, list[dict]], str | None]:
    """Fetches this user's repo via getRepo, decodes it, and returns rows from
    the last `days_back` days, bucketed by record type.

    Rows carry the same columns the jetstream sink writes, built with the same
    parsers, so the two are directly comparable. `ingested_at` is the wall clock
    at fetch time - backfill has no broker clock to read.

    Returns (rows_by_type, error) - error is None on success, otherwise a short
    description of what failed (rows_by_type will be empty buckets).
    """
    rows_by_type = _empty_buckets()

    ingested_at = datetime.now(UTC)
    try:
        repo_bytes = relay_client.com.atproto.sync.get_repo({"did": user["did"]})
    except Exception as e:
        return rows_by_type, f"getRepo failed: {e}"

    try:
        did, rev, records = decode_repo(repo_bytes)
    except Exception as e:
        return rows_by_type, f"CAR/MST decode failed: {e}"

    cutoff = ingested_at - timedelta(days=days_back)

    for uri, (cid, record) in records.items():
        record_type = TARGET_COLLECTIONS.get(record.get("$type"))
        if record_type is None:
            continue

        created_at = parse_created_at(record.get("createdAt"))
        if created_at is None or not is_created_at_valid(created_at, ingested_at):
            continue
        if created_at < cutoff:
            continue

        row = {
            "uri": uri,
            "did": did,
            "cid": cid,
            # Repo-level, so identical across every row of this user.
            "rev": rev,
            "created_at": created_at,
            "ingested_at": ingested_at,
            **_RECORD_PARSERS[record["$type"]](record),
        }
        if not validate_non_null_fields(row, REQUIRED_KEYS[record_type]):
            continue

        rows_by_type[record_type].append(row)

    return rows_by_type, None
