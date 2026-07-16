TARGET_HANDLE = "aoc.bsky.social"

MIN_FOLLOWERS = 1000
MIN_POSTS_LAST_7_DAYS = 5
NUM_USERS_TARGET = 10
WEEKS_BACK = 4
DAYS_BACK = WEEKS_BACK * 7

FOLLOWERS_PAGE_SIZE = 100
PROFILES_BATCH_SIZE = 25
AUTHOR_FEED_CHECK_LIMIT = 30

MAX_FOLLOWERS_TO_EVALUATE = 20_000

TARGET_COLLECTIONS = {
    "app.bsky.feed.post": "posts",
    "app.bsky.feed.like": "likes",
    "app.bsky.feed.repost": "reposts",
    "app.bsky.graph.follow": "follows",
}

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
