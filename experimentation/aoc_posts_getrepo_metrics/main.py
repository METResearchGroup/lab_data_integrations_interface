"""Run the AOC getAuthorFeed + getRepo + AppView metrics experiment.

Run from the repo root:

    PYTHONPATH=. uv run python experimentation/aoc_posts_getrepo_metrics/main.py
"""

from experimentation.aoc_posts_getrepo_metrics.client import (
    create_public_client,
    create_relay_client,
)
from experimentation.aoc_posts_getrepo_metrics.constants import (
    GET_POSTS_MAX_URIS,
    MIN_POSTS,
    TARGET_HANDLE,
)
from experimentation.aoc_posts_getrepo_metrics.enrichment import (
    enrich_rows_with_engagement,
    fetch_engagement_by_uri,
    utc_now_iso,
)
from experimentation.aoc_posts_getrepo_metrics.feed import (
    fetch_latest_post_uris,
    resolve_did,
)
from experimentation.aoc_posts_getrepo_metrics.metrics import derive_rows
from experimentation.aoc_posts_getrepo_metrics.output import write_outputs
from experimentation.aoc_posts_getrepo_metrics.repo import fetch_and_index_posts
from lib.timestamp_utils import get_current_timestamp


def main() -> None:
    """List AOC posts, join getRepo records, enrich AppView counts, and write outputs."""
    sync_timestamp = get_current_timestamp()
    public = create_public_client()
    did = resolve_did(public, TARGET_HANDLE)
    uris = fetch_latest_post_uris(public, did, MIN_POSTS)
    relay = create_relay_client()
    posts_by_uri = fetch_and_index_posts(relay, did)
    rows = derive_rows(uris, posts_by_uri)
    engagement_by_uri = fetch_engagement_by_uri(public, uris)
    counts_read_at = utc_now_iso()
    rows = enrich_rows_with_engagement(rows, engagement_by_uri, counts_read_at)
    metadata = {
        "sync_timestamp": sync_timestamp,
        "target_handle": TARGET_HANDLE,
        "target_did": did,
        "min_posts": MIN_POSTS,
        "post_uri_count": len(uris),
        "rows_with_repo_record": sum(1 for uri in uris if uri in posts_by_uri),
        "rows_missing_repo_record": sum(1 for uri in uris if uri not in posts_by_uri),
        "rows_with_engagement": sum(1 for uri in uris if uri in engagement_by_uri),
        "source_listing": "app.bsky.feed.getAuthorFeed",
        "source_repo": "com.atproto.sync.getRepo",
        "source_engagement": "app.bsky.feed.getPosts",
        "get_repo_calls": 1,
        "get_posts_calls": (
            (len(uris) + GET_POSTS_MAX_URIS - 1) // GET_POSTS_MAX_URIS if uris else 0
        ),
        "counts_read_at": counts_read_at,
    }
    output_dir = write_outputs(rows, metadata, sync_timestamp)
    print(f"Wrote {len(rows)} rows to {output_dir}")


if __name__ == "__main__":
    main()
