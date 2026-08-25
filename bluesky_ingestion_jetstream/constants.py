"""Shared constants."""

from datetime import date, timedelta
from enum import StrEnum


class RecordType(StrEnum):
    """One Iceberg table each. Values are the table and S3 directory names."""

    POSTS = "posts"
    LIKES = "likes"
    REPOSTS = "reposts"
    FOLLOWS = "follows"


POSTS = RecordType.POSTS
LIKES = RecordType.LIKES
REPOSTS = RecordType.REPOSTS
FOLLOWS = RecordType.FOLLOWS

RECORD_TYPES = tuple(RecordType)

# Backfill owns everything before this date, Jetstream everything from it on.
# See strategy_planning/2026-08-18_combining_backfill_and_jetstream.md.
DATA_START_DATE = date(2026, 8, 1)

JETSTREAM_ENDPOINT = "wss://jetstream2.us-east.bsky.network/subscribe"

COLLECTION_TO_RECORD_TYPE = {
    "app.bsky.feed.post": POSTS,
    "app.bsky.feed.like": LIKES,
    "app.bsky.feed.repost": REPOSTS,
    "app.bsky.graph.follow": FOLLOWS,
}

# Filtering server-side means the rest of the firehose never reaches us.
WANTED_COLLECTIONS = tuple(COLLECTION_TO_RECORD_TYPE)

COMMON_REQUIRED_KEYS = ("uri", "did", "created_at", "ingested_at")

# How far `created_at` may sit either side of `ingested_at` before the row is
# dropped. Measured against the broker's clock, so replays stay deterministic.
MAX_CREATED_AT_BACKDATE = timedelta(days=7)
MAX_CREATED_AT_SKEW = timedelta(days=1)

POST_REQUIRED_KEYS = COMMON_REQUIRED_KEYS
LIKE_REQUIRED_KEYS = (*COMMON_REQUIRED_KEYS, "subject_uri")
REPOST_REQUIRED_KEYS = LIKE_REQUIRED_KEYS
FOLLOW_REQUIRED_KEYS = (*COMMON_REQUIRED_KEYS, "subject_did")

REQUIRED_KEYS = {
    POSTS: POST_REQUIRED_KEYS,
    LIKES: LIKE_REQUIRED_KEYS,
    REPOSTS: REPOST_REQUIRED_KEYS,
    FOLLOWS: FOLLOW_REQUIRED_KEYS,
}

# Flush when the buffers hold this many serialized bytes in total, or when the
# oldest rows have been waiting this long.
MAX_BUFFER_SIZE_BYTES = 2 * 1024 * 1024 * 1024
MAX_BUFFER_AGE_SECONDS = 30.0 * 60.0

# How often the flush task re-checks the thresholds.
FLUSH_CHECK_INTERVAL_SECONDS = 1.0

# Which threshold tripped a flush. Reported per flush, so the two are separable.
FLUSH_REASON_SIZE = "size"
FLUSH_REASON_AGE = "age"

# Reconnect backoff, doubling from the first to the second.
INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 60.0
BACKOFF_MULTIPLIER = 2.0

# How far behind the stored cursor a reconnect resumes.
CURSOR_REWIND_MICROSECONDS = 0
