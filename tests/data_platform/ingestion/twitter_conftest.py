from __future__ import annotations

from typing import Any

from data_platform.models.sync import SyncTwitterPostModel

_DEFAULT_TWEET_TEXT = (
    "This is a valid sample tweet for unit tests with enough characters."
)


def mock_tweet_row(tweet_id: str, **overrides: Any) -> dict[str, Any]:
    """Return a dict that satisfies SyncTwitterPostModel (preprocess-ready text)."""
    row: dict[str, Any] = {
        "tweet_id": tweet_id,
        "text": _DEFAULT_TWEET_TEXT,
        "author_id": "100",
        "username": "testuser",
        "created_at": "2026-05-30T00:00:00+00:00",
        "like_count": 1,
        "retweet_count": 0,
        "reply_count": 0,
        "quote_count": 0,
        "url": f"https://x.com/i/web/status/{tweet_id}",
        "keyword": "test",
        "sync_timestamp": "2026_05_30-10:00:00",
    }
    row.update(overrides)
    SyncTwitterPostModel.model_validate(row)
    return row
