"""Shared constants."""

POSTS = "posts"
LIKES = "likes"
REPOSTS = "reposts"
FOLLOWS = "follows"

RECORD_TYPES = (POSTS, LIKES, REPOSTS, FOLLOWS)

COMMON_REQUIRED_KEYS = ("uri", "did", "created_at")

POST_REQUIRED_KEYS = COMMON_REQUIRED_KEYS
LIKE_REQUIRED_KEYS = (*COMMON_REQUIRED_KEYS, "subject_uri")
REPOST_REQUIRED_KEYS = LIKE_REQUIRED_KEYS
FOLLOW_REQUIRED_KEYS = (*COMMON_REQUIRED_KEYS, "subject_did")

# Flush when the buffers hold this many serialized bytes in total, or when the
# oldest rows have been waiting this long.
MAX_BUFFER_SIZE_BYTES = 50 * 1024 * 1024
MAX_BUFFER_AGE_SECONDS = 300.0
