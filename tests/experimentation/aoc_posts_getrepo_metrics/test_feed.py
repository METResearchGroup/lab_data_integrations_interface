"""Tests for author-feed listing helpers."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from experimentation.aoc_posts_getrepo_metrics.feed import (
    fetch_latest_post_uris,
    resolve_did,
)


def _feed_item(uri: str, author_did: str) -> SimpleNamespace:
    return SimpleNamespace(
        post=SimpleNamespace(
            uri=uri,
            author=SimpleNamespace(did=author_did, handle="aoc.bsky.social"),
        )
    )


def _feed_response(items: list[SimpleNamespace], cursor: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(feed=items, cursor=cursor)


class TestResolveDid:
    """Tests for resolve_did()."""

    def test_resolve_did_returns_profile_did(self) -> None:
        """Returns the DID from get_profile."""
        client = MagicMock()
        client.app.bsky.actor.get_profile.return_value = SimpleNamespace(did="did:plc:aoc")

        result = resolve_did(client, "aoc.bsky.social")

        assert result == "did:plc:aoc"
        client.app.bsky.actor.get_profile.assert_called_once_with({"actor": "aoc.bsky.social"})


class TestFetchLatestPostUris:
    """Tests for fetch_latest_post_uris()."""

    def test_fetch_stops_at_min_posts(self) -> None:
        """Stops once min_posts authored URIs are collected across pages."""
        actor = "did:plc:aoc"
        page1 = _feed_response(
            [
                _feed_item("at://did:plc:aoc/app.bsky.feed.post/1", actor),
                _feed_item("at://did:plc:aoc/app.bsky.feed.post/2", actor),
            ],
            cursor="cursor-1",
        )
        page2 = _feed_response(
            [
                _feed_item("at://did:plc:aoc/app.bsky.feed.post/3", actor),
                _feed_item("at://did:plc:aoc/app.bsky.feed.post/4", actor),
            ]
        )
        client = MagicMock()
        client.app.bsky.feed.get_author_feed.side_effect = [page1, page2]

        result = fetch_latest_post_uris(client, actor, 3)

        expected = [
            "at://did:plc:aoc/app.bsky.feed.post/1",
            "at://did:plc:aoc/app.bsky.feed.post/2",
            "at://did:plc:aoc/app.bsky.feed.post/3",
        ]
        assert result == expected
        assert client.app.bsky.feed.get_author_feed.call_count == 2

    def test_fetch_skips_reposts_of_others(self) -> None:
        """Omits feed items whose post author DID is not the actor."""
        actor = "did:plc:aoc"
        response = _feed_response(
            [
                _feed_item("at://did:plc:aoc/app.bsky.feed.post/1", actor),
                _feed_item("at://did:plc:other/app.bsky.feed.post/9", "did:plc:other"),
                _feed_item("at://did:plc:aoc/app.bsky.feed.post/2", actor),
            ]
        )
        client = MagicMock()
        client.app.bsky.feed.get_author_feed.return_value = response

        result = fetch_latest_post_uris(client, actor, 2)

        assert result == [
            "at://did:plc:aoc/app.bsky.feed.post/1",
            "at://did:plc:aoc/app.bsky.feed.post/2",
        ]

    def test_fetch_raises_if_insufficient(self) -> None:
        """Raises ValueError when the feed ends before min_posts."""
        actor = "did:plc:aoc"
        response = _feed_response(
            [
                _feed_item("at://did:plc:aoc/app.bsky.feed.post/1", actor),
                _feed_item("at://did:plc:aoc/app.bsky.feed.post/2", actor),
            ]
        )
        client = MagicMock()
        client.app.bsky.feed.get_author_feed.return_value = response

        with pytest.raises(ValueError, match="2"):
            fetch_latest_post_uris(client, actor, 50)

    def test_fetch_paginates_with_cursor(self) -> None:
        """Passes the first-page cursor into the second get_author_feed call."""
        actor = "did:plc:aoc"
        page1 = _feed_response(
            [_feed_item("at://did:plc:aoc/app.bsky.feed.post/1", actor)],
            cursor="next-page",
        )
        page2 = _feed_response(
            [_feed_item("at://did:plc:aoc/app.bsky.feed.post/2", actor)],
        )
        client = MagicMock()
        client.app.bsky.feed.get_author_feed.side_effect = [page1, page2]

        fetch_latest_post_uris(client, actor, 2)

        second_call_params = client.app.bsky.feed.get_author_feed.call_args_list[1].args[0]
        assert second_call_params["cursor"] == "next-page"

    def test_fetch_skips_duplicate_uris(self) -> None:
        """Counts each post URI once even when the feed repeats it on one page."""
        actor = "did:plc:aoc"
        duplicate_uri = "at://did:plc:aoc/app.bsky.feed.post/1"
        response = _feed_response(
            [
                _feed_item(duplicate_uri, actor),
                _feed_item(duplicate_uri, actor),
                _feed_item("at://did:plc:aoc/app.bsky.feed.post/2", actor),
            ]
        )
        client = MagicMock()
        client.app.bsky.feed.get_author_feed.return_value = response

        result = fetch_latest_post_uris(client, actor, 2)

        assert result == [
            duplicate_uri,
            "at://did:plc:aoc/app.bsky.feed.post/2",
        ]
