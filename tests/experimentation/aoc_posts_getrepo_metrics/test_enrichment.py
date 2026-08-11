"""Tests for AppView engagement enrichment."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from experimentation.aoc_posts_getrepo_metrics.enrichment import (
    enrich_rows_with_engagement,
    fetch_engagement_by_uri,
)
from experimentation.aoc_posts_getrepo_metrics.metrics import derive_row


def _post_view(
    uri: str,
    like_count: int = 1,
    reply_count: int = 2,
    repost_count: int = 3,
    quote_count: int = 4,
    bookmark_count: int = 5,
) -> SimpleNamespace:
    return SimpleNamespace(
        uri=uri,
        like_count=like_count,
        reply_count=reply_count,
        repost_count=repost_count,
        quote_count=quote_count,
        bookmark_count=bookmark_count,
    )


class TestFetchEngagementByUri:
    """Tests for fetch_engagement_by_uri()."""

    def test_fetch_engagement_batches_over_25_uris(self) -> None:
        """Splits requests into batches of at most 25 URIs."""
        uris = [f"at://did:plc:aoc/app.bsky.feed.post/{i}" for i in range(26)]
        client = MagicMock()
        client.app.bsky.feed.get_posts.side_effect = [
            SimpleNamespace(posts=[_post_view(uri) for uri in uris[:25]]),
            SimpleNamespace(posts=[_post_view(uris[25])]),
        ]

        result = fetch_engagement_by_uri(client, uris)

        assert client.app.bsky.feed.get_posts.call_count == 2
        first_batch = client.app.bsky.feed.get_posts.call_args_list[0].args[0]["uris"]
        second_batch = client.app.bsky.feed.get_posts.call_args_list[1].args[0]["uris"]
        assert len(first_batch) == 25
        assert second_batch == [uris[25]]
        assert set(result) == set(uris)

    def test_fetch_engagement_maps_bookmark_to_save_count(self) -> None:
        """Maps AppView bookmark_count onto save_count."""
        uri = "at://did:plc:aoc/app.bsky.feed.post/1"
        client = MagicMock()
        client.app.bsky.feed.get_posts.return_value = SimpleNamespace(
            posts=[_post_view(uri, bookmark_count=9)]
        )

        result = fetch_engagement_by_uri(client, [uri])

        assert result[uri]["save_count"] == 9


class TestEnrichRowsWithEngagement:
    """Tests for enrich_rows_with_engagement()."""

    def test_enrich_rows_fills_counts_and_read_at(self) -> None:
        """Copies engagement counts onto matching rows and stamps counts_read_at."""
        uri = "at://did:plc:aoc/app.bsky.feed.post/1"
        row = derive_row(
            uri,
            {
                "$type": "app.bsky.feed.post",
                "text": "hello",
                "createdAt": "2026-01-01T00:00:00.000Z",
            },
        )
        engagement = {
            uri: {
                "like_count": 10,
                "reply_count": 20,
                "repost_count": 30,
                "quote_count": 40,
                "save_count": 50,
            }
        }

        result = enrich_rows_with_engagement([row], engagement, "2026-08-11T14:00:00+00:00")

        assert result[0]["like_count"] == 10
        assert result[0]["reply_count"] == 20
        assert result[0]["repost_count"] == 30
        assert result[0]["quote_count"] == 40
        assert result[0]["save_count"] == 50
        assert result[0]["counts_read_at"] == "2026-08-11T14:00:00+00:00"
        assert row["like_count"] is None

    def test_enrich_rows_missing_appview_keeps_none_counts(self) -> None:
        """Leaves counts as None when getPosts did not return the URI."""
        uri = "at://did:plc:aoc/app.bsky.feed.post/missing"
        row = derive_row(uri, None)

        result = enrich_rows_with_engagement([row], {}, "2026-08-11T14:00:00+00:00")

        assert result[0]["like_count"] is None
        assert result[0]["counts_read_at"] == "2026-08-11T14:00:00+00:00"
