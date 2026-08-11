"""Frozen constants for the DID sync discovery experiment."""

from experimentation.aoc_followers_backfill import constants as _aoc_constants

TARGET_DIDS = 1000
SMOKE_TARGET_DIDS = 50
DAYS_BACK = 183
MIN_FOLLOWERS = 10
MIN_FOLLOWEES = 10
MIN_ORIGINAL_POSTS_6M = 20
MIN_INTERACTIONS_6M = 20

PLC_EXPORT_URL = "https://plc.directory/export"
PLC_PAGE_SIZE = 1000
PLC_RECENT_LOOKBACK_HOURS = 24
PLC_MAX_LOOKBACK_HOURS = 24 * 30

AOC_HANDLE = _aoc_constants.TARGET_HANDLE
FOLLOWERS_PAGE_SIZE = _aoc_constants.FOLLOWERS_PAGE_SIZE
PROFILES_BATCH_SIZE = _aoc_constants.PROFILES_BATCH_SIZE

ABLATION1_NAME = "ablation1_plc"
ABLATION2_NAME = "ablation2_aoc_bfs"

GETREPO_TIMEOUT_SECONDS = 60.0

# Relay advertises ~6000 getRepo / 300s (~20/s). Stay well under that.
DEFAULT_WORKERS = 2
GETREPO_MIN_INTERVAL_SECONDS = 0.15
GETREPO_MAX_ATTEMPTS = 5
GETREPO_BASE_BACKOFF_SECONDS = 3.0
GETREPO_MAX_BACKOFF_SECONDS = 60.0
GETREPO_RATE_LIMIT_COOLDOWN_SECONDS = 60.0

DISCOVERY_RESULT_KEYS = (
    "ablation",
    "did_count",
    "dids",
    "request_count",
    "runtime_seconds",
    "rate_limit_events",
    "extra",
)

PROFILE_ROW_KEYS = (
    "did",
    "handle",
    "followers",
    "followees",
    "posts",
    "account_created_at",
    "original_posts_6m",
    "interactions_6m",
    "likes_6m",
    "reposts_6m",
    "replies_6m",
    "quotes_6m",
    "bookmarks_6m",
    "valid",
    "invalid_reasons",
    "error",
)

SUMMARY_KEYS = (
    "ablation",
    "did_count",
    "valid_did_count",
    "invalid_did_count",
    "validity_rate",
    "discovery",
    "analysis",
)
