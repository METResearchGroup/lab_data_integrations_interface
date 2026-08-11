"""Tests for derive_stats() null policy and cohort graph rules."""

from datetime import UTC, datetime

from experiments.aoc_getrepo_derived_stats_2026_08_11.derive import derive_stats
from experiments.aoc_getrepo_derived_stats_2026_08_11.discovery import CohortMember
from experiments.aoc_getrepo_derived_stats_2026_08_11.fetch_repos import RepoBundle
from experiments.aoc_getrepo_derived_stats_2026_08_11.records import (
    FollowRow,
    LikeOrRepostRow,
    PostRow,
    ProfileRecord,
)
from experiments.aoc_getrepo_derived_stats_2026_08_11.schemas import DERIVED_STAT_KEYS

WINDOW_START = datetime(2026, 1, 1, tzinfo=UTC)
WINDOW_END = datetime(2026, 7, 2, tzinfo=UTC)


def _member(did: str, handle: str, followers_count: int | None = None) -> CohortMember:
    return CohortMember(
        did=did,
        handle=handle,
        followers_count=followers_count,
        display_name=None,
        is_seed=False,
    )


def _post(**kwargs) -> PostRow:
    defaults = dict(
        uri="at://did:plc:x/app.bsky.feed.post/1",
        created_at="2026-06-01T00:00:00.000Z",
        text="hello",
        is_reply=False,
        reply_parent_uri=None,
        reply_root_uri=None,
        langs="",
        embed_type=None,
        quoted_post_uri=None,
        mentioned_dids="",
        linked_uris="",
    )
    defaults.update(kwargs)
    return PostRow(**defaults)


class TestDeriveStats:
    """Tests for derive_stats()."""

    def test_splits_original_quote_and_reply_with_null_bodies(self):
        """Posts split into original, quote, and reply lists with null bodies."""
        member = _member("did:plc:a", "a.bsky.social")
        bundle = RepoBundle(
            did="did:plc:a",
            handle="a.bsky.social",
            posts=[
                _post(uri="at://did:plc:a/app.bsky.feed.post/o", text="orig"),
                _post(
                    uri="at://did:plc:a/app.bsky.feed.post/q",
                    text="quoting",
                    quoted_post_uri="at://did:plc:b/app.bsky.feed.post/t",
                    embed_type="record",
                ),
                _post(
                    uri="at://did:plc:a/app.bsky.feed.post/r",
                    text="replying",
                    is_reply=True,
                    reply_parent_uri="at://did:plc:b/app.bsky.feed.post/p",
                    reply_root_uri="at://did:plc:b/app.bsky.feed.post/root",
                ),
            ],
        )

        result = derive_stats([member], [bundle], WINDOW_START, WINDOW_END)[0]

        assert [p["text"] for p in result["original_posts"]] == ["orig", "quoting"]
        assert result["quoted_posts"][0]["quoted_post_body"] is None
        assert result["replied_posts"][0]["parent_post_body"] is None
        assert result["replied_posts"][0]["text"] == "replying"

    def test_window_filters_likes_and_reposts(self):
        """Only in-window likes and reposts are kept."""
        member = _member("did:plc:a", "a.bsky.social")
        bundle = RepoBundle(
            did="did:plc:a",
            handle="a.bsky.social",
            likes=[
                LikeOrRepostRow(
                    uri="at://did:plc:a/app.bsky.feed.like/old",
                    created_at="2025-01-01T00:00:00.000Z",
                    subject_uri="at://did:plc:b/app.bsky.feed.post/1",
                    subject_cid="c1",
                ),
                LikeOrRepostRow(
                    uri="at://did:plc:a/app.bsky.feed.like/new",
                    created_at="2026-06-01T00:00:00.000Z",
                    subject_uri="at://did:plc:b/app.bsky.feed.post/2",
                    subject_cid="c2",
                ),
            ],
            reposts=[
                LikeOrRepostRow(
                    uri="at://did:plc:a/app.bsky.feed.repost/new",
                    created_at="2026-05-01T00:00:00.000Z",
                    subject_uri="at://did:plc:b/app.bsky.feed.post/3",
                    subject_cid="c3",
                ),
            ],
        )

        result = derive_stats([member], [bundle], WINDOW_START, WINDOW_END)[0]

        assert len(result["liked_posts"]) == 1
        assert result["liked_posts"][0]["uri"].endswith("/new")
        assert len(result["reposted_posts"]) == 1

    def test_cohort_follow_graph(self):
        """Still-present follows among cohort DIDs populate both lists."""
        a = _member("did:plc:a", "a.bsky.social")
        b = _member("did:plc:b", "b.bsky.social")
        c = _member("did:plc:c", "c.bsky.social")
        bundles = [
            RepoBundle(
                did="did:plc:a",
                handle="a.bsky.social",
                follows=[
                    FollowRow(
                        uri="at://did:plc:a/app.bsky.graph.follow/1",
                        created_at="2026-02-01T00:00:00.000Z",
                        followed_did="did:plc:b",
                    )
                ],
            ),
            RepoBundle(
                did="did:plc:b",
                handle="b.bsky.social",
                follows=[
                    FollowRow(
                        uri="at://did:plc:b/app.bsky.graph.follow/1",
                        created_at="2026-02-01T00:00:00.000Z",
                        followed_did="did:plc:a",
                    ),
                    FollowRow(
                        uri="at://did:plc:b/app.bsky.graph.follow/2",
                        created_at="2026-02-01T00:00:00.000Z",
                        followed_did="did:plc:c",
                    ),
                ],
            ),
            RepoBundle(did="did:plc:c", handle="c.bsky.social", follows=[]),
        ]

        results = {row["did"]: row for row in derive_stats([a, b, c], bundles, WINDOW_START, WINDOW_END)}

        assert results["did:plc:a"]["cohort_followees"] == ["did:plc:b"]
        assert results["did:plc:a"]["cohort_followers"] == ["did:plc:b"]
        assert results["did:plc:b"]["cohort_followees"] == ["did:plc:a", "did:plc:c"]
        assert results["did:plc:c"]["cohort_followers"] == ["did:plc:b"]

    def test_follow_actions_window_and_followees_count(self):
        """follow_actions are windowed; followees_count counts all still-present."""
        member = _member("did:plc:a", "a.bsky.social")
        bundle = RepoBundle(
            did="did:plc:a",
            handle="a.bsky.social",
            follows=[
                FollowRow(
                    uri="at://did:plc:a/app.bsky.graph.follow/old",
                    created_at="2025-01-01T00:00:00.000Z",
                    followed_did="did:plc:z",
                ),
                FollowRow(
                    uri="at://did:plc:a/app.bsky.graph.follow/new",
                    created_at="2026-03-01T00:00:00.000Z",
                    followed_did="did:plc:y",
                ),
            ],
        )

        result = derive_stats([member], [bundle], WINDOW_START, WINDOW_END)[0]

        assert result["followees_count"] == 2
        assert len(result["follow_actions"]) == 1
        assert result["follow_actions"][0]["followed_did"] == "did:plc:y"

    def test_saved_and_unfollow_always_none(self):
        """Unknowable fields stay None."""
        member = _member("did:plc:a", "a.bsky.social")
        bundle = RepoBundle(did="did:plc:a", handle="a.bsky.social")

        result = derive_stats([member], [bundle], WINDOW_START, WINDOW_END)[0]

        assert result["saved_posts"] is None
        assert result["unfollow_actions"] is None

    def test_account_created_at_not_inferred_from_posts(self):
        """Missing profile createdAt stays None even when posts exist."""
        member = _member("did:plc:a", "a.bsky.social")
        bundle = RepoBundle(
            did="did:plc:a",
            handle="a.bsky.social",
            posts=[_post(created_at="2020-01-01T00:00:00.000Z")],
            profile=ProfileRecord(display_name="A", description="bio", created_at=None),
        )

        result = derive_stats([member], [bundle], WINDOW_START, WINDOW_END)[0]

        assert result["account_created_at"] is None
        assert result["display_name"] == "A"
        assert result["bio"] == "bio"

    def test_followers_count_from_appview_member(self):
        """AppView followers_count is copied onto the derived object."""
        member = _member("did:plc:a", "a.bsky.social", followers_count=123)
        bundle = RepoBundle(did="did:plc:a", handle="a.bsky.social")

        result = derive_stats([member], [bundle], WINDOW_START, WINDOW_END)[0]

        assert result["followers_count"] == 123

    def test_errored_bundle_keeps_null_policy(self):
        """Failed repos still emit full keys with mandatory nulls."""
        member = _member("did:plc:a", "a.bsky.social", followers_count=1)
        bundle = RepoBundle(
            did="did:plc:a",
            handle="a.bsky.social",
            error="getRepo failed: boom",
        )

        result = derive_stats([member], [bundle], WINDOW_START, WINDOW_END)[0]

        assert list(result.keys()) == list(DERIVED_STAT_KEYS)
        assert result["saved_posts"] is None
        assert result["unfollow_actions"] is None
        assert result["original_posts"] == []
        assert result["followees_count"] is None
        assert result["display_name"] is None
        assert result["followers_count"] == 1
