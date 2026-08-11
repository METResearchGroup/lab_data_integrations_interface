"""Tests for relay getRepo post indexing."""

from unittest.mock import MagicMock

import pytest

from experimentation.aoc_posts_getrepo_metrics import repo as repo_module
from experimentation.aoc_posts_getrepo_metrics.repo import fetch_and_index_posts

DID = "did:plc:aoc"
POST_URI_1 = f"at://{DID}/app.bsky.feed.post/1"
POST_URI_2 = f"at://{DID}/app.bsky.feed.post/2"
LIKE_URI = f"at://{DID}/app.bsky.feed.like/1"
FOLLOW_URI = f"at://{DID}/app.bsky.graph.follow/1"


def _decoded_records() -> tuple[str, dict[str, dict]]:
    return DID, {
        POST_URI_1: {"$type": "app.bsky.feed.post", "text": "one", "createdAt": "2026-01-01T00:00:00Z"},
        POST_URI_2: {"$type": "app.bsky.feed.post", "text": "two", "createdAt": "2026-01-02T00:00:00Z"},
        LIKE_URI: {"$type": "app.bsky.feed.like", "createdAt": "2026-01-03T00:00:00Z"},
        FOLLOW_URI: {"$type": "app.bsky.graph.follow", "createdAt": "2026-01-04T00:00:00Z"},
    }


class TestFetchAndIndexPosts:
    """Tests for fetch_and_index_posts()."""

    def test_fetch_and_index_calls_get_repo_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Calls get_repo exactly once for the account DID."""
        relay = MagicMock()
        relay.com.atproto.sync.get_repo.return_value = b"fake-car"
        monkeypatch.setattr(repo_module, "decode_repo", lambda _bytes: _decoded_records())

        fetch_and_index_posts(relay, DID)

        relay.com.atproto.sync.get_repo.assert_called_once_with({"did": DID})

    def test_fetch_and_index_keeps_only_posts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Drops like and follow records from the index."""
        relay = MagicMock()
        relay.com.atproto.sync.get_repo.return_value = b"fake-car"
        monkeypatch.setattr(repo_module, "decode_repo", lambda _bytes: _decoded_records())

        result = fetch_and_index_posts(relay, DID)

        assert set(result) == {POST_URI_1, POST_URI_2}

    def test_fetch_and_index_keys_are_at_uris(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Every indexed key is a post at-URI."""
        relay = MagicMock()
        relay.com.atproto.sync.get_repo.return_value = b"fake-car"
        monkeypatch.setattr(repo_module, "decode_repo", lambda _bytes: _decoded_records())

        result = fetch_and_index_posts(relay, DID)

        for uri in result:
            assert uri.startswith("at://")
            assert "/app.bsky.feed.post/" in uri

    def test_fetch_and_index_raises_on_did_mismatch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Raises ValueError when the decoded repo DID does not match the request."""
        relay = MagicMock()
        relay.com.atproto.sync.get_repo.return_value = b"fake-car"
        monkeypatch.setattr(
            repo_module,
            "decode_repo",
            lambda _bytes: ("did:plc:other", {POST_URI_1: {"$type": "app.bsky.feed.post"}}),
        )

        with pytest.raises(ValueError, match="did:plc:other"):
            fetch_and_index_posts(relay, DID)
