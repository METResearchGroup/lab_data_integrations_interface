from __future__ import annotations

from typing import Any

from data_platform.ingestion import sync_reddit
from tests.data_platform.constants import VALID_REDDIT_DATASET_ID


def minimal_reddit_sync_config() -> dict[str, Any]:
    return {
        "dataset_id": VALID_REDDIT_DATASET_ID,
        "name": "test",
        "description": "test",
        "date": "2026-05-31",
        "record_types": [sync_reddit.COMMENTS_RECORD_TYPE, sync_reddit.POSTS_RECORD_TYPE],
        "ingestion_params": {
            "comments_dedupe_policy": ["current_run", "prior_runs_all_datasets"],
            "posts_dedupe_policy": ["current_run", "prior_runs_all_datasets"],
            "subreddits": ["AlphaSub", "BetaSub"],
            "listing": "hot",
            "limit_per_subreddit": 2,
            "comments_per_post": 5,
            "min_comment_body_length": 10,
        },
    }


def mock_comment_row(
    comment_fullname: str,
    *,
    post_reddit_id: str = "abc123",
    subreddit: str = "alphasub",
) -> dict[str, Any]:
    return {
        "post_reddit_id": post_reddit_id,
        "post_reddit_fullname": f"t3_{post_reddit_id}",
        "subreddit": subreddit,
        "comment_id": comment_fullname.removeprefix("t1_"),
        "comment_fullname": comment_fullname,
        "parent_id": f"t3_{post_reddit_id}",
        "author": "user",
        "body": "comment text long enough",
        "score": 1,
        "created_utc": "2026-05-30T00:00:00+00:00",
        "permalink": f"/r/{subreddit}/comments/{post_reddit_id}/x/{comment_fullname}/",
        "depth": 0,
        "comment_rank": 1,
        "sync_timestamp": "2026_05_30-10:00:00",
    }


def mock_post_row(
    reddit_fullname: str,
    *,
    subreddit: str = "alphasub",
) -> dict[str, Any]:
    reddit_id = reddit_fullname.removeprefix("t3_")
    return {
        "reddit_id": reddit_id,
        "reddit_fullname": reddit_fullname,
        "subreddit": subreddit,
        "title": "title",
        "selftext": "body",
        "author": "user",
        "score": 1,
        "upvote_ratio": 0.5,
        "num_comments": 1,
        "created_utc": "2026-05-30T00:00:00+00:00",
        "permalink": f"/r/{subreddit}/comments/{reddit_id}/title/",
        "url": f"https://reddit.com/r/{subreddit}/comments/{reddit_id}/title/",
        "is_self": True,
        "sync_timestamp": "2026_05_30-10:00:00",
    }
