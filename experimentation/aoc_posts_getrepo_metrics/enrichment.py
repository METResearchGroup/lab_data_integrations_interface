"""AppView engagement enrichment via ``app.bsky.feed.getPosts``."""

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from experimentation.aoc_posts_getrepo_metrics.constants import GET_POSTS_MAX_URIS


def _chunked(uris: list[str], size: int) -> list[list[str]]:
    return [uris[i : i + size] for i in range(0, len(uris), size)]


def fetch_engagement_by_uri(client: Any, post_uris: list[str]) -> dict[str, dict]:
    """Fetch AppView engagement counts for post URIs in batches of 25.

    Parameters
    ----------
    client
        Public AppView client.
    post_uris
        Post at-URIs to hydrate.

    Returns
    -------
    dict[str, dict]
        Mapping of URI to engagement fields. Missing posts are omitted.
    """
    engagement_by_uri: dict[str, dict] = {}
    for batch in _chunked(post_uris, GET_POSTS_MAX_URIS):
        if not batch:
            continue
        response = client.app.bsky.feed.get_posts({"uris": batch})
        for post in response.posts:
            engagement_by_uri[post.uri] = {
                "like_count": post.like_count,
                "reply_count": post.reply_count,
                "repost_count": post.repost_count,
                "quote_count": post.quote_count,
                "save_count": post.bookmark_count,
            }
    return engagement_by_uri


def enrich_rows_with_engagement(
    rows: list[dict],
    engagement_by_uri: dict[str, dict],
    counts_read_at: str,
) -> list[dict]:
    """Return copies of rows with AppView engagement fields filled when present.

    Parameters
    ----------
    rows
        Metrics rows from ``derive_rows``.
    engagement_by_uri
        Output of ``fetch_engagement_by_uri``.
    counts_read_at
        ISO-8601 timestamp for when the counts were read.

    Returns
    -------
    list[dict]
        New row dicts. Rows without AppView hits keep engagement counts as
        ``None`` but still receive ``counts_read_at``.
    """
    enriched: list[dict] = []
    for row in rows:
        new_row = deepcopy(row)
        new_row["counts_read_at"] = counts_read_at
        engagement = engagement_by_uri.get(row["post_uri"])
        if engagement is not None:
            new_row.update(engagement)
        enriched.append(new_row)
    return enriched


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()
