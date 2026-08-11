"""Cohort size, time window, and collection constants for the AOC getRepo experiment."""

TARGET_HANDLE = "aoc.bsky.social"
FOLLOWER_SAMPLE_SIZE = 50
COHORT_SIZE_MAX = 1 + FOLLOWER_SAMPLE_SIZE
DAYS_BACK = 182
FOLLOWERS_PAGE_SIZE = 100
PROFILES_BATCH_SIZE = 25

TARGET_COLLECTIONS = {
    "app.bsky.feed.post": "posts",
    "app.bsky.feed.like": "likes",
    "app.bsky.feed.repost": "reposts",
    "app.bsky.graph.follow": "follows",
}

PROFILE_COLLECTION = "app.bsky.actor.profile"

POST_CSV_FIELDNAMES = [
    "author_handle",
    "author_did",
    "uri",
    "created_at",
    "text",
    "is_reply",
    "reply_parent_uri",
    "reply_root_uri",
    "langs",
    "embed_type",
    "quoted_post_uri",
    "mentioned_dids",
    "linked_uris",
]

LIKE_REPOST_CSV_FIELDNAMES = [
    "author_handle",
    "author_did",
    "uri",
    "created_at",
    "subject_uri",
    "subject_cid",
]

FOLLOW_CSV_FIELDNAMES = [
    "author_handle",
    "author_did",
    "uri",
    "created_at",
    "followed_did",
]
