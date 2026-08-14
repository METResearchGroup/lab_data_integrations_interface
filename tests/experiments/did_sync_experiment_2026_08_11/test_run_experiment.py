"""Tests for experiment orchestration helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from experiments.did_sync_experiment_2026_08_11.analyze import AnalyzeMeta, ProfileStats
from experiments.did_sync_experiment_2026_08_11.constants import ABLATION1_NAME, SUMMARY_KEYS
from experiments.did_sync_experiment_2026_08_11.discover import DiscoveryResult
from experiments.did_sync_experiment_2026_08_11.run_experiment import (
    build_summary,
    write_results_md,
)


class TestBuildSummary:
    """Tests for build_summary()."""

    def test_counts_valid_dids(self):
        """Verifies summary counts and frozen keys."""
        discovery = DiscoveryResult(
            ablation=ABLATION1_NAME,
            dids=["did:plc:a", "did:plc:b"],
            request_count=2,
            runtime_seconds=1.5,
        )
        profiles = [
            ProfileStats(did="did:plc:a", valid=True),
            ProfileStats(did="did:plc:b", valid=False),
        ]
        analysis = AnalyzeMeta(
            getrepo_request_count=2,
            getrepo_error_count=0,
            getrepo_rate_limit_event_count=0,
            getrepo_runtime_seconds=3.0,
            appview_profile_request_count=1,
        )

        summary = build_summary(ABLATION1_NAME, discovery, profiles, analysis)

        assert set(SUMMARY_KEYS) <= set(summary.keys())
        assert summary["did_count"] == 2
        assert summary["valid_did_count"] == 1
        assert summary["validity_rate"] == 0.5


class TestWriteResultsMd:
    """Tests for write_results_md()."""

    def test_includes_both_ablation_counts(self):
        """Verifies RESULTS text includes DID and valid DID counts."""
        summaries = [
            {
                "ablation": "ablation1_plc",
                "did_count": 50,
                "valid_did_count": 5,
                "invalid_did_count": 45,
                "validity_rate": 0.1,
                "discovery": {
                    "request_count": 1,
                    "runtime_seconds": 0.5,
                    "rate_limit_event_count": 0,
                    "extra": {},
                },
                "analysis": {
                    "getrepo_request_count": 50,
                    "getrepo_error_count": 0,
                    "getrepo_rate_limit_event_count": 0,
                    "getrepo_runtime_seconds": 10.0,
                    "appview_profile_request_count": 2,
                },
            },
            {
                "ablation": "ablation2_aoc_bfs",
                "did_count": 50,
                "valid_did_count": 12,
                "invalid_did_count": 38,
                "validity_rate": 0.24,
                "discovery": {
                    "request_count": 3,
                    "runtime_seconds": 1.2,
                    "rate_limit_event_count": 0,
                    "extra": {"seed_handle": "aoc.bsky.social"},
                },
                "analysis": {
                    "getrepo_request_count": 50,
                    "getrepo_error_count": 1,
                    "getrepo_rate_limit_event_count": 0,
                    "getrepo_runtime_seconds": 12.0,
                    "appview_profile_request_count": 2,
                },
            },
        ]

        text = write_results_md(summaries, datetime(2026, 8, 11, 12, 0, 0, tzinfo=UTC))

        assert "ablation2_aoc_bfs produced the most valid DIDs" in text
        assert "| ablation1_plc | 50 | 5 |" in text
        assert "| ablation2_aoc_bfs | 50 | 12 |" in text


class TestMergeSummaries:
    """Tests for merge_summaries()."""

    def test_preserves_order_and_replaces_matching(self):
        """Verifies merged summaries keep ablation order and overwrite by name."""
        from experiments.did_sync_experiment_2026_08_11.run_experiment import merge_summaries

        existing = [
            {"ablation": "ablation1_plc", "valid_did_count": 1},
            {"ablation": "ablation2_aoc_bfs", "valid_did_count": 183},
        ]
        new = [
            {"ablation": "ablation3_plc_old", "valid_did_count": 1},
            {"ablation": "ablation4_list_repos", "valid_did_count": 20},
        ]

        merged = merge_summaries(existing, new)

        assert [item["ablation"] for item in merged] == [
            "ablation1_plc",
            "ablation2_aoc_bfs",
            "ablation3_plc_old",
            "ablation4_list_repos",
        ]
        assert merged[3]["valid_did_count"] == 20
