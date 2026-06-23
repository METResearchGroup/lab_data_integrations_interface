"""Platform ID column bindings shared across preprocessing, features, and curation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformIdBinding:
    records_id_column: str
    text_column: str
    feature_file_id_column: str = "uri"
    records_file_key: str = "posts"


BLUESKY_BINDING = PlatformIdBinding(
    records_id_column="uri",
    text_column="text",
    feature_file_id_column="uri",
    records_file_key="posts",
)

REDDIT_BINDING = PlatformIdBinding(
    records_id_column="comment_fullname",
    text_column="body",
    feature_file_id_column="uri",
    records_file_key="comments",
)

TWITTER_BINDING = PlatformIdBinding(
    records_id_column="tweet_id",
    text_column="text",
    feature_file_id_column="uri",
    records_file_key="posts",
)
