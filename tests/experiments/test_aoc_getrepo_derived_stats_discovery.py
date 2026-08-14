"""Mocked AppView tests for discover_cohort()."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from experiments.aoc_getrepo_derived_stats_2026_08_11.discovery import discover_cohort


def _profile(did: str, handle: str, followers_count=100, display_name=None):
    return SimpleNamespace(
        did=did,
        handle=handle,
        followers_count=followers_count,
        display_name=display_name,
    )


def _follower(did: str, handle: str):
    return SimpleNamespace(did=did, handle=handle)


class TestDiscoverCohort:
    """Tests for discover_cohort()."""

    def test_fifty_followers_yields_cohort_of_fifty_one(self):
        """AOC plus 50 newest followers produce a 51-member cohort."""
        client = MagicMock()
        client.app.bsky.actor.get_profile.return_value = _profile(
            "did:plc:aoc", "aoc.bsky.social", followers_count=1000, display_name="AOC"
        )
        followers = [_follower(f"did:plc:u{i}", f"u{i}.bsky.social") for i in range(50)]
        client.app.bsky.graph.get_followers.return_value = SimpleNamespace(
            followers=followers, cursor=None
        )
        client.app.bsky.actor.get_profiles.return_value = SimpleNamespace(
            profiles=[
                _profile(f"did:plc:u{i}", f"u{i}.bsky.social", followers_count=i + 1)
                for i in range(50)
            ]
        )

        result = discover_cohort(client)

        assert len(result.members) == 51
        assert result.target_did == "did:plc:aoc"
        assert result.members[0].is_seed is True
        assert result.members[0].did == "did:plc:aoc"
        assert all(not member.is_seed for member in result.members[1:])
        assert result.members[1].followers_count == 1

    def test_short_follower_list_does_not_pad(self):
        """Fewer than 50 followers yields 1 + available members."""
        client = MagicMock()
        client.app.bsky.actor.get_profile.return_value = _profile("did:plc:aoc", "aoc.bsky.social")
        client.app.bsky.graph.get_followers.return_value = SimpleNamespace(
            followers=[
                _follower("did:plc:u0", "u0.bsky.social"),
                _follower("did:plc:u1", "u1.bsky.social"),
                _follower("did:plc:u2", "u2.bsky.social"),
            ],
            cursor=None,
        )
        client.app.bsky.actor.get_profiles.return_value = SimpleNamespace(
            profiles=[
                _profile("did:plc:u0", "u0.bsky.social", followers_count=10),
                _profile("did:plc:u1", "u1.bsky.social", followers_count=20),
                _profile("did:plc:u2", "u2.bsky.social", followers_count=30),
            ]
        )

        result = discover_cohort(client)

        assert len(result.members) == 4

    def test_stops_at_fifty_across_pages(self):
        """Paging stops once 50 followers are collected."""
        client = MagicMock()
        client.app.bsky.actor.get_profile.return_value = _profile("did:plc:aoc", "aoc.bsky.social")
        page1 = [_follower(f"did:plc:p1_{i}", f"p1_{i}.bsky.social") for i in range(100)]
        page2 = [_follower(f"did:plc:p2_{i}", f"p2_{i}.bsky.social") for i in range(20)]
        client.app.bsky.graph.get_followers.side_effect = [
            SimpleNamespace(followers=page1, cursor="next"),
            SimpleNamespace(followers=page2, cursor=None),
        ]
        client.app.bsky.actor.get_profiles.return_value = SimpleNamespace(
            profiles=[
                _profile(f"did:plc:p1_{i}", f"p1_{i}.bsky.social", followers_count=1)
                for i in range(50)
            ]
        )

        result = discover_cohort(client)

        assert len(result.members) == 51
        assert client.app.bsky.graph.get_followers.call_count == 1

    def test_missing_followers_count_becomes_none(self):
        """Profiles without followers_count map to None."""
        client = MagicMock()
        client.app.bsky.actor.get_profile.return_value = _profile(
            "did:plc:aoc", "aoc.bsky.social", followers_count=5
        )
        client.app.bsky.graph.get_followers.return_value = SimpleNamespace(
            followers=[_follower("did:plc:u0", "u0.bsky.social")],
            cursor=None,
        )
        bare = SimpleNamespace(did="did:plc:u0", handle="u0.bsky.social")
        client.app.bsky.actor.get_profiles.return_value = SimpleNamespace(profiles=[bare])

        result = discover_cohort(client)

        assert result.members[1].followers_count is None

    def test_does_not_construct_relay_client(self):
        """Discovery never builds a relay client."""
        client = MagicMock()
        client.app.bsky.actor.get_profile.return_value = _profile("did:plc:aoc", "aoc.bsky.social")
        client.app.bsky.graph.get_followers.return_value = SimpleNamespace(
            followers=[], cursor=None
        )

        with patch("experimentation.aoc_followers_backfill.client.create_relay_client") as relay:
            discover_cohort(client)
            relay.assert_not_called()
