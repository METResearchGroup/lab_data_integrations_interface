"""Tests for experiment constants and CLI contracts."""

from experiments.did_sync_experiment_2026_08_11.analyze import ProfileStats
from experiments.did_sync_experiment_2026_08_11.constants import (
    ABLATION1_NAME,
    ABLATION2_NAME,
    AOC_HANDLE,
    DAYS_BACK,
    DEFAULT_WORKERS,
    DISCOVERY_RESULT_KEYS,
    FOLLOWERS_PAGE_SIZE,
    MIN_FOLLOWEES,
    MIN_FOLLOWERS,
    MIN_INTERACTIONS_6M,
    MIN_ORIGINAL_POSTS_6M,
    PLC_EXPORT_URL,
    PLC_PAGE_SIZE,
    PLC_RECENT_LOOKBACK_HOURS,
    PROFILE_ROW_KEYS,
    PROFILES_BATCH_SIZE,
    SMOKE_TARGET_DIDS,
    SUMMARY_KEYS,
    TARGET_DIDS,
)
from experiments.did_sync_experiment_2026_08_11.discover import DiscoveryResult, RateLimitEvent
from experiments.did_sync_experiment_2026_08_11.run_experiment import build_parser, resolve_target


class TestConstants:
    """Tests for frozen experiment constants."""

    def test_target_and_validity_thresholds(self):
        """Verifies DID targets and validity thresholds match the plan."""
        assert TARGET_DIDS == 1000
        assert SMOKE_TARGET_DIDS == 50
        assert DAYS_BACK == 183
        assert MIN_FOLLOWERS == 10
        assert MIN_FOLLOWEES == 10
        assert MIN_ORIGINAL_POSTS_6M == 20
        assert MIN_INTERACTIONS_6M == 20

    def test_plc_and_aoc_wiring(self):
        """Verifies PLC URL/page size and AOC handle reuse."""
        assert PLC_EXPORT_URL == "https://plc.directory/export"
        assert PLC_PAGE_SIZE == 1000
        assert PLC_RECENT_LOOKBACK_HOURS == 24
        assert AOC_HANDLE == "aoc.bsky.social"
        assert FOLLOWERS_PAGE_SIZE == 100
        assert PROFILES_BATCH_SIZE == 25
        assert ABLATION1_NAME == "ablation1_plc"
        assert ABLATION2_NAME == "ablation2_aoc_bfs"
        assert DEFAULT_WORKERS == 2


class TestDiscoveryResultToDict:
    """Tests for DiscoveryResult.to_dict()."""

    def test_includes_frozen_keys(self):
        """Verifies serialized discovery JSON includes the frozen schema keys."""
        result = DiscoveryResult(
            ablation=ABLATION1_NAME,
            dids=["did:plc:a"],
            request_count=1,
            runtime_seconds=0.5,
            rate_limit_events=[
                RateLimitEvent(
                    source="plc.directory/export",
                    at_unix=1.0,
                    status_code=429,
                    detail="rate limited",
                    retry_after="5",
                )
            ],
            extra={"pages": 1},
        )

        payload = result.to_dict()

        assert set(DISCOVERY_RESULT_KEYS) <= set(payload.keys())
        assert payload["did_count"] == 1
        assert payload["dids"] == ["did:plc:a"]


class TestProfileStatsToDict:
    """Tests for ProfileStats.to_dict()."""

    def test_includes_frozen_keys(self):
        """Verifies serialized profile rows include the frozen schema keys."""
        row = ProfileStats(did="did:plc:a")

        payload = row.to_dict()

        assert set(PROFILE_ROW_KEYS) <= set(payload.keys())


class TestSummaryKeys:
    """Tests for summary schema constants."""

    def test_summary_key_set(self):
        """Verifies summary key contract from the plan."""
        assert SUMMARY_KEYS == (
            "ablation",
            "did_count",
            "valid_did_count",
            "invalid_did_count",
            "validity_rate",
            "discovery",
            "analysis",
        )


class TestBuildParser:
    """Tests for build_parser()."""

    def test_help_lists_required_flags(self):
        """Verifies --help documents target, workers, only, and smoke."""
        parser = build_parser()
        help_text = parser.format_help()

        assert "--target" in help_text
        assert "--workers" in help_text
        assert "--only" in help_text
        assert "--smoke" in help_text


class TestResolveTarget:
    """Tests for resolve_target()."""

    def test_explicit_target_wins(self):
        """Verifies an explicit --target overrides --smoke."""
        assert resolve_target(75, smoke=True) == 75

    def test_smoke_without_target(self):
        """Verifies --smoke alone selects SMOKE_TARGET_DIDS."""
        assert resolve_target(None, smoke=True) == SMOKE_TARGET_DIDS

    def test_default_without_smoke(self):
        """Verifies the default target is TARGET_DIDS."""
        assert resolve_target(None, smoke=False) == TARGET_DIDS
