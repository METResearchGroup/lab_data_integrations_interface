"""PRAW client helpers for the Reddit subreddit post fetch experiment."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import praw
import praw.models
import prawcore.exceptions

from lib.load_env_vars import EnvVarsContainer

logger = logging.getLogger(__name__)

CSV_FIELDNAMES: list[str] = [
    "reddit_id",
    "reddit_fullname",
    "subreddit",
    "title",
    "selftext",
    "author",
    "score",
    "upvote_ratio",
    "num_comments",
    "created_utc",
    "permalink",
    "url",
    "is_self",
    "sync_timestamp",
]


def init_reddit() -> praw.Reddit:
    """Build a PRAW Reddit instance using script-app password grant credentials."""
    client_id = EnvVarsContainer.get_env_var("REDDIT_CLIENT_ID", required=True)
    client_secret = EnvVarsContainer.get_env_var("REDDIT_SECRET", required=True)
    username = EnvVarsContainer.get_env_var("REDDIT_USERNAME", required=True)
    password = EnvVarsContainer.get_env_var("REDDIT_PASSWORD", required=True)
    user_agent = f"lab_data_integrations:v0.1 (by /u/{username})"
    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        username=username,
        password=password,
        user_agent=user_agent,
    )


def submission_to_row(post: praw.models.Submission, sync_timestamp: str) -> dict[str, object]:
    """Normalize a PRAW Submission to a flat dict matching the CSV schema."""
    author = "[deleted]" if post.author is None else str(post.author)
    created_utc = datetime.fromtimestamp(post.created_utc, tz=UTC).isoformat()
    return {
        "reddit_id": post.id,
        "reddit_fullname": post.name,
        "subreddit": post.subreddit.display_name,
        "title": post.title,
        "selftext": post.selftext,
        "author": author,
        "score": post.score,
        "upvote_ratio": post.upvote_ratio,
        "num_comments": post.num_comments,
        "created_utc": created_utc,
        "permalink": post.permalink,
        "url": post.url,
        "is_self": post.is_self,
        "sync_timestamp": sync_timestamp,
    }


def fetch_subreddit_posts(
    reddit: praw.Reddit,
    subreddit: str,
    limit: int,
    sync_timestamp: str,
) -> list[dict[str, object]]:
    """Fetch hot posts from a subreddit and return normalized row dicts."""
    try:
        posts = reddit.subreddit(subreddit).hot(limit=limit)
        return [submission_to_row(post, sync_timestamp) for post in posts]
    except prawcore.exceptions.NotFound:
        logger.warning("Subreddit not found: %s", subreddit)
        return []
