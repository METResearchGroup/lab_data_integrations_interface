"""Shared constants."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

POSTS = "posts"
LIKES = "likes"
REPOSTS = "reposts"
FOLLOWS = "follows"

RECORD_TYPES = (POSTS, LIKES, REPOSTS, FOLLOWS)

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

# `created_at` is the client's own clock and the Iceberg partition key, so a row
# claiming 1970 or 2087 mints a partition directory holding a single tiny file,
# permanently. Rows outside this window are dropped rather than clamped: a
# clamped row would sit in a real partition wearing a timestamp nobody chose,
# which is worse than not having it.
#
# The floor is absolute and deliberately generous -- comfortably before the
# network existed, so it cannot reject a genuine record. Tightening it to
# something relative (`ingested_at - 30 days`) would suppress far more partition
# sprawl, at the cost of dropping legitimately republished records.
EARLIEST_VALID_CREATED_AT = datetime(2022, 1, 1, tzinfo=UTC)

# The ceiling is relative to `ingested_at`, the broker's clock, not to
# `datetime.now()`: it keeps the check deterministic in tests and stable under
# replay, where a cursor rewind redelivers old events to a much later wall clock.
# A create should reach the firehose within seconds of being made, so a full day
# of slack is pure allowance for misconfigured device clocks.
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
MAX_BUFFER_AGE_SECONDS = 30.0

DATA_DIR = Path(__file__).parent / "data"

# Reconnect backoff, doubling from the first to the second.
INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 60.0
BACKOFF_MULTIPLIER = 2.0
