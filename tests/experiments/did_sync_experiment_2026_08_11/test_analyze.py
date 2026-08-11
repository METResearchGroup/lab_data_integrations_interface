"""Tests for getRepo enrichment and validity classification."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from experiments.did_sync_experiment_2026_08_11.analyze import (
    ProfileStats,
    analyze_dids,
    apply_validity,
    count_activity_from_records,
)
from experiments.did_sync_experiment_2026_08_11.constants import DAYS_BACK


def _cutoff() -> datetime:
    return datetime(2026, 8, 11, 12, 0, 0, tzinfo=UTC) - timedelta(days=DAYS_BACK)


def _in_window_ts() -> str:
    return "2026-07-01T00:00:00.000Z"


def _old_ts() -> str:
    return "2024-01-01T00:00:00.000Z"


def _records_for_valid_account() -> dict[str, dict]:
    records: dict[str, dict] = {}
    for i in range(10):
        records[f"at://did:plc:x/app.bsky.graph.follow/{i}"] = {
            "$type": "app.bsky.graph.follow",
            "createdAt": _in_window_ts(),
            "subject": f"did:plc:y{i}",
        }
    for i in range(20):
        records[f"at://did:plc:x/app.bsky.feed.post/{i}"] = {
            "$type": "app.bsky.feed.post",
            "createdAt": _in_window_ts(),
            "text": f"post {i}",
        }
    for i in range(20):
        records[f"at://did:plc:x/app.bsky.feed.like/{i}"] = {
            "$type": "app.bsky.feed.like",
            "createdAt": _in_window_ts(),
            "subject": {"uri": f"at://did:plc:z/app.bsky.feed.post/{i}", "cid": "bafy"},
        }
    return records


class TestCountActivityFromRecords:
    """Tests for count_activity_from_records()."""

    def test_quote_counts_as_original_and_interaction(self):
        """Verifies a non-reply quote increments original posts and interactions."""
        records = {
            "at://did:plc:x/app.bsky.feed.post/1": {
                "$type": "app.bsky.feed.post",
                "createdAt": _in_window_ts(),
                "text": "quote",
                "embed": {"$type": "app.bsky.embed.record", "record": {"uri": "at://x"}},
            }
        }

        counts = count_activity_from_records(records, _cutoff())

        assert counts.original_posts_6m == 1
        assert counts.quotes_6m == 1
        assert counts.interactions_6m == 1
        assert counts.replies_6m == 0

    def test_reply_counts_as_interaction_not_original(self):
        """Verifies replies increment interactions but not original posts."""
        records = {
            "at://did:plc:x/app.bsky.feed.post/1": {
                "$type": "app.bsky.feed.post",
                "createdAt": _in_window_ts(),
                "text": "reply",
                "reply": {
                    "parent": {"uri": "at://did:plc:y/app.bsky.feed.post/1"},
                    "root": {"uri": "at://did:plc:y/app.bsky.feed.post/1"},
                },
            }
        }

        counts = count_activity_from_records(records, _cutoff())

        assert counts.original_posts_6m == 0
        assert counts.replies_6m == 1
        assert counts.interactions_6m == 1

    def test_missing_bookmarks_contribute_zero(self):
        """Verifies missing bookmark collections do not raise and count as zero."""
        records = {
            "at://did:plc:x/app.bsky.feed.post/1": {
                "$type": "app.bsky.feed.post",
                "createdAt": _in_window_ts(),
                "text": "hi",
            }
        }

        counts = count_activity_from_records(records, _cutoff())

        assert counts.bookmarks_6m == 0


class TestParseBskyDatetime:
    """Tests for _parse_bsky_datetime()."""

    def test_naive_timestamp_becomes_utc(self):
        """Verifies offset-naive createdAt values compare safely as UTC."""
        from experiments.did_sync_experiment_2026_08_11.analyze import _parse_bsky_datetime

        parsed = _parse_bsky_datetime("2026-07-01T00:00:00")

        assert parsed is not None
        assert parsed.tzinfo is not None
        assert parsed.utcoffset().total_seconds() == 0

    """Tests for apply_validity()."""

    def test_valid_when_all_thresholds_met(self):
        """Verifies validity is true when all four thresholds are met."""
        stats = ProfileStats(
            did="did:plc:x",
            followers=10,
            followees=10,
            original_posts_6m=20,
            interactions_6m=20,
        )

        result = apply_validity(stats)

        assert result.valid is True
        assert result.invalid_reasons == []

    def test_invalid_when_original_posts_below_threshold(self):
        """Verifies validity is false with a reason when original posts are low."""
        stats = ProfileStats(
            did="did:plc:x",
            followers=10,
            followees=10,
            original_posts_6m=19,
            interactions_6m=20,
        )

        result = apply_validity(stats)

        assert result.valid is False
        assert "original_posts_6m<20" in result.invalid_reasons


class TestIsRateLimited:
    """Tests for _is_rate_limited()."""

    def test_status_429_is_rate_limited(self):
        """Verifies HTTP 429 is treated as a rate limit."""
        from experiments.did_sync_experiment_2026_08_11.analyze import _is_rate_limited

        exc = Exception("boom")
        exc.status_code = 429
        assert _is_rate_limited(exc) is True

    def test_xrpc_rate_limit_exceeded_is_rate_limited(self):
        """Verifies XRPC RateLimitExceeded is treated as a rate limit."""
        from experiments.did_sync_experiment_2026_08_11.analyze import _is_rate_limited

        content = SimpleNamespace(error="RateLimitExceeded", message="Too Many Requests")
        response = SimpleNamespace(status_code=429, content=content)
        exc = Exception("wrapped")
        exc.response = response
        assert _is_rate_limited(exc) is True

    def test_does_not_treat_ratelimit_headers_as_rate_limit(self):
        """Verifies ordinary errors whose str() dumps RateLimit headers are not 429s."""
        from experiments.did_sync_experiment_2026_08_11.analyze import _is_rate_limited

        content = SimpleNamespace(
            error="RepoTakendown",
            message="Repo has been takendown: did:plc:x",
        )
        response = SimpleNamespace(
            status_code=400,
            content=content,
            headers={
                "ratelimit-limit": "6000",
                "ratelimit-remaining": "5999",
                "ratelimit-policy": "6000;w=300",
            },
        )
        exc = Exception(
            "Response(success=False, status_code=400, content=XrpcError("
            "error='RepoTakendown', message='Repo has been takendown'), "
            "headers={'ratelimit-limit': '6000', 'ratelimit-remaining': '5999'})"
        )
        exc.response = response
        assert _is_rate_limited(exc) is False


class TestFetchRepoBytes:
    """Tests for _fetch_repo_bytes()."""

    def test_retries_rate_limit_then_succeeds(self):
        """Verifies a 429 is retried until getRepo succeeds."""
        from experiments.did_sync_experiment_2026_08_11.analyze import (
            RelayRequestPacer,
            _fetch_repo_bytes,
        )

        relay = MagicMock()
        rate_limited = Exception("RateLimitExceeded")
        rate_limited.status_code = 429
        relay.com.atproto.sync.get_repo.side_effect = [rate_limited, b"car-bytes"]
        sleeps: list[float] = []
        pacer = RelayRequestPacer(0.0)

        repo_bytes, error, was_rate_limited = _fetch_repo_bytes(
            "did:plc:x",
            relay,
            pacer,
            sleeps.append,
        )

        assert repo_bytes == b"car-bytes"
        assert error is None
        assert was_rate_limited is True
        assert sleeps[0] == 3.0
        assert relay.com.atproto.sync.get_repo.call_count == 2

    def test_retries_network_error_then_succeeds(self):
        """Verifies NetworkError-style failures are retried until getRepo succeeds."""
        from experiments.did_sync_experiment_2026_08_11.analyze import (
            RelayRequestPacer,
            _fetch_repo_bytes,
        )

        class FakeNetworkError(Exception):
            """Stand-in for atproto NetworkError without importing the SDK type."""

        FakeNetworkError.__name__ = "NetworkError"
        relay = MagicMock()
        relay.com.atproto.sync.get_repo.side_effect = [
            FakeNetworkError("RequestException"),
            b"car-bytes",
        ]
        sleeps: list[float] = []
        pacer = RelayRequestPacer(0.0)

        repo_bytes, error, was_rate_limited = _fetch_repo_bytes(
            "did:plc:x",
            relay,
            pacer,
            sleeps.append,
        )

        assert repo_bytes == b"car-bytes"
        assert error is None
        assert was_rate_limited is False
        assert sleeps[0] == 3.0
        assert relay.com.atproto.sync.get_repo.call_count == 2


class TestAnalyzeDids:
    """Tests for analyze_dids()."""

    def test_appview_follower_overlay(self, monkeypatch):
        """Verifies AppView follower counts overlay onto analyzed rows."""
        records = _records_for_valid_account()
        monkeypatch.setattr(
            "experiments.did_sync_experiment_2026_08_11.analyze.decode_repo",
            lambda _repo_bytes: ("did:plc:x", records),
        )
        relay = MagicMock()
        relay.com.atproto.sync.get_repo.return_value = b"fake-car"
        public = MagicMock()
        public.app.bsky.actor.get_profiles.return_value = SimpleNamespace(
            profiles=[
                SimpleNamespace(
                    did="did:plc:x",
                    handle="user.bsky.social",
                    followers_count=42,
                    created_at="2025-01-01T00:00:00.000Z",
                )
            ]
        )

        rows, meta = analyze_dids(
            ["did:plc:x"],
            workers=1,
            relay_client=relay,
            public_client=public,
            now=datetime(2026, 8, 11, 12, 0, 0, tzinfo=UTC),
        )

        assert len(rows) == 1
        assert rows[0].followers == 42
        assert rows[0].handle == "user.bsky.social"
        assert rows[0].valid is True
        assert meta.appview_profile_request_count == 1
        assert meta.getrepo_request_count == 1
