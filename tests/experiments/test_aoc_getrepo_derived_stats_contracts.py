"""Contract tests for AOC getRepo derived-stats constants and schema helpers."""

from experiments.aoc_getrepo_derived_stats_2026_08_11 import constants, schemas


class TestConstants:
    """Tests for cohort and window constants."""

    def test_follower_sample_and_window(self):
        """Locks sample size 50, 182-day window, and AOC handle."""
        assert constants.TARGET_HANDLE == "aoc.bsky.social"
        assert constants.FOLLOWER_SAMPLE_SIZE == 50
        assert constants.DAYS_BACK == 182
        assert constants.COHORT_SIZE_MAX == 51


class TestDerivedStatKeys:
    """Tests for DERIVED_STAT_KEYS ordering."""

    def test_exact_ordered_keys(self):
        """Derived-stat documents use the frozen key order from the plan."""
        expected = (
            "did",
            "handle",
            "display_name",
            "bio",
            "account_created_at",
            "window_start",
            "window_end",
            "original_posts",
            "liked_posts",
            "reposted_posts",
            "quoted_posts",
            "replied_posts",
            "saved_posts",
            "cohort_followers",
            "cohort_followees",
            "followers_count",
            "followees_count",
            "follow_actions",
            "unfollow_actions",
        )
        assert schemas.DERIVED_STAT_KEYS == expected


class TestNullUnknowable:
    """Tests for unknowable-field sentinels."""

    def test_saved_and_unfollow_are_none_not_empty_list(self):
        """Unknowable fields must be None, never []."""
        assert schemas.null_unknowable() is None
        shell = schemas.empty_derived_stats_shell(
            did="did:plc:test",
            handle="test.bsky.social",
            window_start="2026-01-01T00:00:00+00:00",
            window_end="2026-07-02T00:00:00+00:00",
        )
        assert shell["saved_posts"] is None
        assert shell["unfollow_actions"] is None
        assert not isinstance(shell["saved_posts"], list)
        assert not isinstance(shell["unfollow_actions"], list)


class TestEmptyDerivedStatsShell:
    """Tests for empty_derived_stats_shell()."""

    def test_knowable_lists_empty_and_quote_reply_body_slots_absent_until_filled(self):
        """Knowable lists start empty; shell has all keys and mandatory nulls."""
        result = schemas.empty_derived_stats_shell(
            did="did:plc:alice",
            handle="alice.bsky.social",
            window_start="2026-01-01T00:00:00+00:00",
            window_end="2026-07-02T00:00:00+00:00",
        )
        assert list(result.keys()) == list(schemas.DERIVED_STAT_KEYS)
        assert result["original_posts"] == []
        assert result["liked_posts"] == []
        assert result["reposted_posts"] == []
        assert result["quoted_posts"] == []
        assert result["replied_posts"] == []
        assert result["cohort_followers"] == []
        assert result["cohort_followees"] == []
        assert result["follow_actions"] == []
        assert result["saved_posts"] is None
        assert result["unfollow_actions"] is None
        assert result["followers_count"] is None
        assert result["followees_count"] is None
        assert result["account_created_at"] is None
