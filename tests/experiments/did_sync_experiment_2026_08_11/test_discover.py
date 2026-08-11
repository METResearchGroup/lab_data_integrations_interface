"""Tests for DID discovery helpers."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from email.message import Message
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.error import HTTPError

from experiments.did_sync_experiment_2026_08_11.constants import (
    ABLATION1_NAME,
    ABLATION2_NAME,
    AOC_HANDLE,
    DISCOVERY_RESULT_KEYS,
)
from experiments.did_sync_experiment_2026_08_11.discover import (
    discover_aoc_bfs_dids,
    discover_plc_dids,
)


def _jsonl(ops: list[dict]) -> bytes:
    return ("\n".join(json.dumps(op) for op in ops) + "\n").encode("utf-8")


def _response(body: bytes, headers: dict[str, str] | None = None) -> MagicMock:
    resp = MagicMock()
    resp.read.return_value = body
    resp.headers = headers or {}
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = None
    return resp


def _follower(did: str) -> SimpleNamespace:
    return SimpleNamespace(did=did, handle=f"{did}.handle")


class TestDiscoverPlcDids:
    """Tests for discover_plc_dids()."""

    def test_skips_duplicate_dids_across_ops(self):
        """Verifies create/update ops for the same DID count once."""
        now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=UTC)
        ops = [
            {"did": "did:plc:a", "createdAt": "2026-08-11T11:00:00.000Z"},
            {"did": "did:plc:a", "createdAt": "2026-08-11T11:01:00.000Z"},
            {"did": "did:plc:b", "createdAt": "2026-08-11T11:02:00.000Z"},
            {"did": "did:plc:c", "createdAt": "2026-08-11T11:03:00.000Z"},
        ]
        urlopen = MagicMock(return_value=_response(_jsonl(ops)))

        result = discover_plc_dids(target=3, now=now, urlopen=urlopen, sleep=lambda _: None)

        assert result.dids == ["did:plc:a", "did:plc:b", "did:plc:c"]
        assert result.request_count >= 1

    def test_first_request_includes_nonempty_after(self):
        """Verifies the first PLC request uses a recent after cursor."""
        now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=UTC)
        ops = [{"did": "did:plc:a", "createdAt": "2026-08-11T11:30:00.000Z"}]
        urlopen = MagicMock(return_value=_response(_jsonl(ops)))

        discover_plc_dids(target=1, now=now, urlopen=urlopen, sleep=lambda _: None)

        first_url = urlopen.call_args_list[0].args[0]
        assert "after=" in first_url
        assert "2026-08-10T12%3A00%3A00.000Z" in first_url

    def test_stops_at_target_unique_dids(self):
        """Verifies paging stops once target unique DIDs are collected."""
        now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=UTC)
        ops = [
            {"did": f"did:plc:{i}", "createdAt": f"2026-08-11T11:0{i}:00.000Z"} for i in range(5)
        ]
        urlopen = MagicMock(return_value=_response(_jsonl(ops)))

        result = discover_plc_dids(target=3, now=now, urlopen=urlopen, sleep=lambda _: None)

        assert len(result.dids) == 3
        assert result.runtime_seconds > 0
        assert result.ablation == ABLATION1_NAME

    def test_http_429_records_rate_limit_and_retries(self):
        """Verifies a 429 appends a rate limit event and a retry still returns DIDs."""
        now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=UTC)
        headers = Message()
        headers["Retry-After"] = "1"
        error = HTTPError(
            url="https://plc.directory/export",
            code=429,
            msg="Too Many Requests",
            hdrs=headers,
            fp=io.BytesIO(b""),
        )
        ok = _response(_jsonl([{"did": "did:plc:a", "createdAt": "2026-08-11T11:30:00.000Z"}]))
        urlopen = MagicMock(side_effect=[error, ok])
        sleeps: list[float] = []

        result = discover_plc_dids(target=1, now=now, urlopen=urlopen, sleep=sleeps.append)

        assert result.dids == ["did:plc:a"]
        assert len(result.rate_limit_events) == 1
        assert result.rate_limit_events[0].status_code == 429
        assert sleeps == [1.0]

    def test_to_dict_includes_frozen_keys(self):
        """Verifies DiscoveryResult.to_dict includes frozen schema keys."""
        now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=UTC)
        ops = [{"did": "did:plc:a", "createdAt": "2026-08-11T11:30:00.000Z"}]
        urlopen = MagicMock(return_value=_response(_jsonl(ops)))

        payload = discover_plc_dids(
            target=1, now=now, urlopen=urlopen, sleep=lambda _: None
        ).to_dict()

        assert set(DISCOVERY_RESULT_KEYS) <= set(payload.keys())
        assert payload["extra"]["initial_after"]
        assert payload["extra"]["pages"] >= 1


class TestDiscoverAocBfsDids:
    """Tests for discover_aoc_bfs_dids()."""

    def _mock_client(self, seed_did: str, pages_by_actor: dict[str, list[list[str]]]):
        client = MagicMock()
        client.app.bsky.actor.get_profile.return_value = SimpleNamespace(
            did=seed_did,
            handle=AOC_HANDLE,
            followers_count=100,
        )
        cursors: dict[str, int] = {actor: 0 for actor in pages_by_actor}

        def get_followers(params: dict):
            actor = params["actor"]
            page_index = cursors[actor]
            pages = pages_by_actor[actor]
            if page_index >= len(pages):
                return SimpleNamespace(followers=[], cursor=None)
            page = pages[page_index]
            cursors[actor] = page_index + 1
            next_cursor = f"c{page_index + 1}" if page_index + 1 < len(pages) else None
            return SimpleNamespace(
                followers=[_follower(did) for did in page],
                cursor=next_cursor,
            )

        client.app.bsky.graph.get_followers.side_effect = get_followers
        return client

    def test_bfs_orders_seed_followers_before_deeper_followers(self):
        """Verifies depth-1 followers are collected before depth-2 followers."""
        seed = "did:plc:aoc"
        client = self._mock_client(
            seed,
            {
                seed: [["did:plc:f1", "did:plc:f2"]],
                "did:plc:f1": [["did:plc:d2a"]],
                "did:plc:f2": [["did:plc:d2b"]],
            },
        )

        result = discover_aoc_bfs_dids(target=4, client=client, sleep=lambda _: None)

        assert result.dids[:2] == ["did:plc:f1", "did:plc:f2"]
        assert set(result.dids[2:]) == {"did:plc:d2a", "did:plc:d2b"}
        assert result.extra["max_depth_reached"] >= 1

    def test_stops_at_exact_target(self):
        """Verifies collection stops at target even when more followers remain."""
        seed = "did:plc:aoc"
        many = [f"did:plc:f{i}" for i in range(60)]
        client = self._mock_client(seed, {seed: [many]})

        result = discover_aoc_bfs_dids(target=50, client=client, sleep=lambda _: None)

        assert len(result.dids) == 50
        assert seed not in result.dids

    def test_ignores_duplicate_follower_dids(self):
        """Verifies duplicate follower DIDs across pages are ignored."""
        seed = "did:plc:aoc"
        client = self._mock_client(
            seed,
            {seed: [["did:plc:f1", "did:plc:f1", "did:plc:f2"]]},
        )

        result = discover_aoc_bfs_dids(target=2, client=client, sleep=lambda _: None)

        assert result.dids == ["did:plc:f1", "did:plc:f2"]

    def test_rate_limit_on_followers_page_retries(self):
        """Verifies a rate limited followers page records an event and retries."""
        seed = "did:plc:aoc"
        client = MagicMock()
        client.app.bsky.actor.get_profile.return_value = SimpleNamespace(
            did=seed, handle=AOC_HANDLE, followers_count=10
        )
        client.app.bsky.graph.get_followers.side_effect = [
            Exception("429 rate limit"),
            SimpleNamespace(followers=[_follower("did:plc:f1")], cursor=None),
        ]
        sleeps: list[float] = []

        result = discover_aoc_bfs_dids(target=1, client=client, sleep=sleeps.append)

        assert result.dids == ["did:plc:f1"]
        assert len(result.rate_limit_events) == 1
        assert sleeps == [5.0]

    def test_extra_seed_handle(self):
        """Verifies extra seed_handle is aoc.bsky.social."""
        seed = "did:plc:aoc"
        client = self._mock_client(seed, {seed: [["did:plc:f1"]]})

        result = discover_aoc_bfs_dids(target=1, client=client, sleep=lambda _: None)

        assert result.extra["seed_handle"] == AOC_HANDLE
        assert result.ablation == ABLATION2_NAME
