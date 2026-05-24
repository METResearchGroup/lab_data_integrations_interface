"""PRAW client helpers for the Reddit subreddit post fetch experiment."""

from __future__ import annotations

import logging
from collections.abc import Iterator
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

COMMENT_CSV_FIELDNAMES: list[str] = [
    "post_reddit_id",
    "post_reddit_fullname",
    "subreddit",
    "comment_id",
    "comment_fullname",
    "parent_id",
    "author",
    "body",
    "score",
    "created_utc",
    "permalink",
    "depth",
    "comment_rank",
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


def is_eligible_comment(comment: praw.models.Comment, min_body_length: int) -> bool:
    """Return True if a comment passes stickied/mod/length filters."""
    if comment.stickied:
        return False
    if comment.distinguished is not None:
        return False
    if len((comment.body or "").strip()) < min_body_length:
        return False
    return True


def comment_to_row(
    comment: praw.models.Comment,
    submission: praw.models.Submission,
    sync_timestamp: str,
    *,
    depth: int,
    comment_rank: int,
) -> dict[str, object]:
    """Normalize a PRAW Comment to a flat dict matching the comment CSV schema."""
    author = "[deleted]" if comment.author is None else str(comment.author)
    created_utc = datetime.fromtimestamp(comment.created_utc, tz=UTC).isoformat()
    return {
        "post_reddit_id": submission.id,
        "post_reddit_fullname": submission.name,
        "subreddit": submission.subreddit.display_name,
        "comment_id": comment.id,
        "comment_fullname": comment.name,
        "parent_id": comment.parent_id,
        "author": author,
        "body": comment.body,
        "score": comment.score,
        "created_utc": created_utc,
        "permalink": comment.permalink,
        "depth": depth,
        "comment_rank": comment_rank,
        "sync_timestamp": sync_timestamp,
    }


def _has_more_comments(comments_forest: praw.models.CommentForest) -> bool:
    return any(isinstance(comment, praw.models.MoreComments) for comment in comments_forest)


def _expand_more_comments(comments_forest: praw.models.CommentForest) -> None:
    """Fetch MoreComments batches until none remain or expansion stalls."""
    while _has_more_comments(comments_forest):
        previous_len = len(comments_forest)
        comments_forest.replace_more(limit=32)
        if len(comments_forest) == previous_len:
            break


def _walk_comments_in_order(
    comments_forest: praw.models.CommentForest,
    depth: int = 0,
) -> Iterator[tuple[praw.models.Comment, int]]:
    """Yield (comment, depth) in Reddit default display order via depth-first walk."""
    comments_forest.replace_more(limit=0)
    _expand_more_comments(comments_forest)

    idx = 0
    while idx < len(comments_forest):
        if _has_more_comments(comments_forest):
            _expand_more_comments(comments_forest)

        if idx >= len(comments_forest):
            break

        comment = comments_forest[idx]
        idx += 1
        if isinstance(comment, praw.models.MoreComments):
            continue

        yield comment, depth
        if comment.replies:
            yield from _walk_comments_in_order(comment.replies, depth + 1)


def fetch_post_comments(
    submission: praw.models.Submission,
    max_comments: int,
    min_body_length: int,
    sync_timestamp: str,
) -> list[dict[str, object]]:
    """Collect up to max_comments eligible comments for a submission."""
    rows: list[dict[str, object]] = []
    submission.comments.replace_more(limit=0)

    for comment, depth in _walk_comments_in_order(submission.comments):
        if len(rows) >= max_comments:
            break
        if not is_eligible_comment(comment, min_body_length):
            continue
        rows.append(
            comment_to_row(
                comment,
                submission,
                sync_timestamp,
                depth=depth,
                comment_rank=len(rows) + 1,
            )
        )

    return rows


def fetch_subreddit_posts(
    reddit: praw.Reddit,
    subreddit: str,
    limit: int,
    sync_timestamp: str,
    *,
    comments_per_post: int = 100,
    min_comment_body_length: int = 30,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Fetch hot posts and eligible comments; return (post_rows, comment_rows)."""
    try:
        posts = reddit.subreddit(subreddit).hot(limit=limit)
        post_rows: list[dict[str, object]] = []
        comment_rows: list[dict[str, object]] = []
        for post in posts:
            post_rows.append(submission_to_row(post, sync_timestamp))
            try:
                comment_rows.extend(
                    fetch_post_comments(
                        post,
                        max_comments=comments_per_post,
                        min_body_length=min_comment_body_length,
                        sync_timestamp=sync_timestamp,
                    )
                )
            except Exception:
                logger.warning(
                    "Failed to fetch comments for post %s in r/%s",
                    post.id,
                    subreddit,
                    exc_info=True,
                )
        return post_rows, comment_rows
    except prawcore.exceptions.NotFound:
        logger.warning("Subreddit not found: %s", subreddit)
        return [], []
