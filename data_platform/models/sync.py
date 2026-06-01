from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SyncBlueskyPostModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uri: str
    url: str
    author_handle: str
    text: str
    created_at: str
    like_count: int
    repost_count: int
    reply_count: int
    quote_count: int


class SyncRedditPostModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reddit_id: str
    reddit_fullname: str
    subreddit: str
    title: str
    selftext: str
    author: str
    score: int
    upvote_ratio: float
    num_comments: int
    created_utc: str
    permalink: str
    url: str
    is_self: bool
    sync_timestamp: str


class SyncRedditCommentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    post_reddit_id: str
    post_reddit_fullname: str
    subreddit: str
    comment_id: str
    comment_fullname: str
    parent_id: str
    author: str
    body: str
    score: int
    created_utc: str
    permalink: str
    depth: int
    comment_rank: int
    sync_timestamp: str
