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
