"""Shared constants."""

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

COMMON_REQUIRED_KEYS = ("uri", "did", "created_at")

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
MAX_BUFFER_AGE_SECONDS = 300.0

DATA_DIR = Path(__file__).parent / "data"

# Reconnect backoff, doubling from the first to the second.
INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 60.0
BACKOFF_MULTIPLIER = 2.0
