"""Tests for getRepo fetch, classify, and window filtering."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from experiments.aoc_getrepo_derived_stats_2026_08_11.discovery import CohortMember
from experiments.aoc_getrepo_derived_stats_2026_08_11.fetch_repos import (
    classify_records,
    fetch_cohort_repos,
    fetch_one_repo,
)
from experiments.aoc_getrepo_derived_stats_2026_08_11.records import (
    extract_quoted_post_uri,
    filter_rows_by_window,
)


def _member(did: str = "did:plc:alice", handle: str = "alice.bsky.social") -> CohortMember:
    return CohortMember(
        did=did,
        handle=handle,
        followers_count=10,
        display_name="Alice",
        is_seed=False,
    )


class TestClassifyRecords:
    """Tests for classify_records()."""

    def test_splits_collections_and_keeps_profile(self):
        """Posts, likes, reposts, follows, and profile are separated."""
        records = {
            "at://did:plc:alice/app.bsky.feed.post/1": {
                "$type": "app.bsky.feed.post",
                "text": "hi",
                "createdAt": "2026-07-01T00:00:00.000Z",
            },
            "at://did:plc:alice/app.bsky.feed.like/1": {
                "$type": "app.bsky.feed.like",
                "createdAt": "2026-07-01T00:00:00.000Z",
                "subject": {"uri": "at://did:plc:bob/app.bsky.feed.post/x", "cid": "bafy1"},
            },
            "at://did:plc:alice/app.bsky.feed.repost/1": {
                "$type": "app.bsky.feed.repost",
                "createdAt": "2026-07-01T00:00:00.000Z",
                "subject": {"uri": "at://did:plc:bob/app.bsky.feed.post/y", "cid": "bafy2"},
            },
            "at://did:plc:alice/app.bsky.graph.follow/1": {
                "$type": "app.bsky.graph.follow",
                "createdAt": "2026-07-01T00:00:00.000Z",
                "subject": "did:plc:bob",
            },
            "at://did:plc:alice/app.bsky.actor.profile/self": {
                "$type": "app.bsky.actor.profile",
                "displayName": "Alice",
                "description": "bio",
                "createdAt": "2024-01-01T00:00:00.000Z",
            },
        }

        posts, likes, reposts, follows, profile = classify_records(records)

        assert len(posts) == 1
        assert len(likes) == 1
        assert len(reposts) == 1
        assert len(follows) == 1
        assert profile is not None
        assert profile.display_name == "Alice"
        assert profile.description == "bio"


class TestQuoteAndReplyExtraction:
    """Tests for quote URI and reply parent extraction."""

    def test_quote_and_reply_uris_without_hydration(self):
        """Quote and reply metadata come from the actor record only."""
        quote_embed = {
            "$type": "app.bsky.embed.record",
            "record": {"uri": "at://did:plc:bob/app.bsky.feed.post/q", "cid": "bafyq"},
        }
        assert extract_quoted_post_uri(quote_embed) == "at://did:plc:bob/app.bsky.feed.post/q"

        nested = {
            "$type": "app.bsky.embed.recordWithMedia",
            "record": {"record": {"uri": "at://did:plc:bob/app.bsky.feed.post/qm", "cid": "bafym"}},
        }
        assert extract_quoted_post_uri(nested) == "at://did:plc:bob/app.bsky.feed.post/qm"

        records = {
            "at://did:plc:alice/app.bsky.feed.post/r": {
                "$type": "app.bsky.feed.post",
                "text": "reply",
                "createdAt": "2026-07-01T00:00:00.000Z",
                "reply": {
                    "parent": {"uri": "at://did:plc:bob/app.bsky.feed.post/p", "cid": "c1"},
                    "root": {"uri": "at://did:plc:bob/app.bsky.feed.post/root", "cid": "c2"},
                },
            }
        }
        posts, *_ = classify_records(records)
        assert posts[0].reply_parent_uri == "at://did:plc:bob/app.bsky.feed.post/p"
        assert posts[0].reply_root_uri == "at://did:plc:bob/app.bsky.feed.post/root"


class TestFilterRowsByWindow:
    """Tests for filter_rows_by_window()."""

    def test_keeps_in_window_posts_and_leaves_profile_untouched(self):
        """Window filter drops old posts but does not touch profile separately."""
        records = {
            "at://did:plc:alice/app.bsky.feed.post/old": {
                "$type": "app.bsky.feed.post",
                "text": "old",
                "createdAt": "2025-01-01T00:00:00.000Z",
            },
            "at://did:plc:alice/app.bsky.feed.post/new": {
                "$type": "app.bsky.feed.post",
                "text": "new",
                "createdAt": "2026-07-01T00:00:00.000Z",
            },
            "at://did:plc:alice/app.bsky.actor.profile/self": {
                "$type": "app.bsky.actor.profile",
                "displayName": "Alice",
            },
        }
        posts, _, _, _, profile = classify_records(records)
        window_start = datetime(2026, 1, 1, tzinfo=UTC)
        window_end = datetime(2026, 7, 2, tzinfo=UTC)
        filtered = filter_rows_by_window(posts, window_start, window_end)

        assert [row.text for row in filtered] == ["new"]
        assert profile is not None
        assert profile.display_name == "Alice"


class TestFetchOneRepo:
    """Tests for fetch_one_repo()."""

    def test_success_path_uses_imported_decode(self):
        """Successful getRepo + decode populates the bundle."""
        member = _member()
        relay = MagicMock()
        relay.com.atproto.sync.get_repo.return_value = b"car-bytes"
        decoded = {
            "at://did:plc:alice/app.bsky.feed.post/1": {
                "$type": "app.bsky.feed.post",
                "text": "hi",
                "createdAt": "2026-07-01T00:00:00.000Z",
            },
            "at://did:plc:alice/app.bsky.actor.profile/self": {
                "$type": "app.bsky.actor.profile",
                "displayName": "Alice",
            },
        }

        with patch(
            "experiments.aoc_getrepo_derived_stats_2026_08_11.fetch_repos.decode_repo",
            return_value=("did:plc:alice", decoded),
        ) as decode:
            bundle = fetch_one_repo(member, relay)

        decode.assert_called_once_with(b"car-bytes")
        assert bundle.error is None
        assert len(bundle.posts) == 1
        assert bundle.profile is not None
        assert bundle.profile.display_name == "Alice"

    def test_get_repo_failure_sets_error_and_empties(self):
        """Relay failures become per-DID errors without raising."""
        member = _member()
        relay = MagicMock()
        relay.com.atproto.sync.get_repo.side_effect = RuntimeError("boom")

        bundle = fetch_one_repo(member, relay)

        assert bundle.error is not None
        assert "getRepo failed" in bundle.error
        assert bundle.posts == []
        assert bundle.profile is None

    def test_classification_failure_sets_error(self):
        """Malformed records become per-DID errors without stopping the caller."""
        member = _member()
        relay = MagicMock()
        relay.com.atproto.sync.get_repo.return_value = b"car-bytes"
        malformed = {
            "at://did:plc:alice/app.bsky.feed.post/1": {
                "$type": "app.bsky.feed.post",
                "text": "bad reply",
                "createdAt": "2026-07-01T00:00:00.000Z",
                "reply": {"parent": "not-a-strong-ref"},
            }
        }

        with patch(
            "experiments.aoc_getrepo_derived_stats_2026_08_11.fetch_repos.decode_repo",
            return_value=("did:plc:alice", malformed),
        ):
            bundle = fetch_one_repo(member, relay)

        assert bundle.error is not None
        assert "record classification failed" in bundle.error
        assert bundle.posts == []


class TestFetchCohortRepos:
    """Tests for fetch_cohort_repos()."""

    def test_continues_after_one_failure(self):
        """One failed DID does not stop the cohort loop."""
        members = (_member("did:plc:a", "a.bsky.social"), _member("did:plc:b", "b.bsky.social"))
        relay = MagicMock()

        def get_repo(params):
            if params["did"] == "did:plc:a":
                raise RuntimeError("fail a")
            return b"ok"

        relay.com.atproto.sync.get_repo.side_effect = get_repo

        with patch(
            "experiments.aoc_getrepo_derived_stats_2026_08_11.fetch_repos.decode_repo",
            return_value=(
                "did:plc:b",
                {
                    "at://did:plc:b/app.bsky.feed.post/1": {
                        "$type": "app.bsky.feed.post",
                        "text": "ok",
                        "createdAt": "2026-07-01T00:00:00.000Z",
                    }
                },
            ),
        ):
            bundles = fetch_cohort_repos(members, relay)

        assert bundles[0].error is not None
        assert bundles[1].error is None
        assert len(bundles[1].posts) == 1


class TestImportsDecodeRepo:
    """Guards against forking MST decode into the experiment package."""

    def test_fetch_module_imports_shared_mst(self):
        """fetch_repos.py must import decode_repo from the shared MST module."""
        source = Path("experiments/aoc_getrepo_derived_stats_2026_08_11/fetch_repos.py").read_text(
            encoding="utf-8"
        )
        assert "from experimentation.aoc_followers_backfill.mst import decode_repo" in source
        assert "def _walk_node" not in source
