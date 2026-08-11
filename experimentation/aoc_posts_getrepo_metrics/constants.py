"""Constants for the AOC getAuthorFeed + getRepo metrics experiment."""

from enum import StrEnum
from pathlib import Path

TARGET_HANDLE = "aoc.bsky.social"
MIN_POSTS = 50
AUTHOR_FEED_PAGE_SIZE = 100
RELAY_BASE_URL = "https://bsky.network"
PUBLIC_APPVIEW_BASE_URL = "https://public.api.bsky.app"
OUTPUT_ROOT = Path(__file__).parent / "data"
POST_COLLECTION = "app.bsky.feed.post"
DELETED_STATUS_UNKNOWN = "unknown"
EMBED_IMAGES = "app.bsky.embed.images"
EMBED_VIDEO = "app.bsky.embed.video"
EMBED_RECORD_WITH_MEDIA = "app.bsky.embed.recordWithMedia"
METRICS_CSV_FILENAME = "posts_metrics.csv"
METADATA_FILENAME = "metadata.json"
GET_POSTS_MAX_URIS = 25


class PostType(StrEnum):
    """Whether a post starts a thread or replies inside one."""

    ORIGINAL = "original"
    REPLY = "reply"


CSV_FIELDNAMES = [
    "post_uri",
    "post_rkey",
    "created_at",
    "deleted",
    "deleted_at",
    "post_type",
    "has_image",
    "has_video",
    "langs",
    "like_count",
    "reply_count",
    "repost_count",
    "quote_count",
    "save_count",
    "counts_read_at",
]
