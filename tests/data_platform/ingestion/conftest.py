from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from data_platform.ingestion import sync_bluesky
from tests.data_platform.constants import VALID_DATASET_ID


def mock_post(uri: str) -> SimpleNamespace:
    return SimpleNamespace(
        uri=uri,
        author=SimpleNamespace(handle="user.bsky.social"),
        record=SimpleNamespace(text="post text", created_at="2026-05-30T00:00:00.000Z"),
        like_count=0,
        repost_count=0,
        reply_count=0,
        quote_count=0,
    )


def mock_search_response(
    posts: list[SimpleNamespace],
    *,
    hits_total: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(posts=posts, cursor=None, hits_total=hits_total)


def minimal_sync_config() -> dict[str, Any]:
    return {
        "dataset_id": VALID_DATASET_ID,
        "name": "test",
        "description": "test",
        "date": "2026-05-30",
        "record_types": [sync_bluesky.POSTS_RECORD_TYPE],
        "ingestion_params": {
            "limit": 2,
            "sort": "latest",
            "keywords": ["alpha", "beta"],
        },
    }
