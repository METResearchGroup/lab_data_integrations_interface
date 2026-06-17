"""Sync Reddit comments from YAML config to raw CSV storage.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/ingestion/sync_reddit.py \\
        --config data_platform/ingestion/configs/reddit/mirrorview.yaml

Resume the latest in-progress run for a dataset:

    PYTHONPATH=. uv run python data_platform/ingestion/sync_reddit.py \\
        --config data_platform/ingestion/configs/reddit/mirrorview.yaml --resume

Resume a specific raw run timestamp:

    PYTHONPATH=. uv run python data_platform/ingestion/sync_reddit.py \\
        --config data_platform/ingestion/configs/reddit/mirrorview.yaml --resume \\
        --run-dir 2026_05_30-12:00:00

Ingestion YAML must include `dataset_id` (e.g. reddit_<uuid>).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import praw
import praw.models
import prawcore.exceptions
from praw.models.comment_forest import CommentForest

from data_platform.ingestion.reddit_retry import retry_reddit_request
from data_platform.ingestion.sync_checkpoint import (
    TaskStatus,
    build_base_sync_metadata,
    ensure_dataset_manifest,
    mark_task_completed,
    mark_task_failed,
    mark_task_in_progress,
    parse_max_rows,
    prepare_sync_run,
    record_type_to_filename,
    require_dataset_id,
    run_checkpointed_sync,
    run_sync_cli,
)
from data_platform.ingestion.sync_clients import init_reddit_client
from data_platform.utils.config_paths import load_yaml_config
from data_platform.utils.deduplication import DedupeConfig, DedupeSession
from data_platform.utils.storage import RedditStorageManager, StorageStage

COMMENTS_RECORD_TYPE = "reddit.comment"
POSTS_RECORD_TYPE = "reddit.post"
DEFAULT_LISTING = "hot"
VALID_LISTING_TIME_FILTERS = frozenset({"all", "day", "hour", "month", "week", "year"})

logger = logging.getLogger(__name__)


def submission_to_row(post: praw.models.Submission, sync_timestamp: str) -> dict[str, Any]:
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
) -> dict[str, Any]:
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


def _has_more_comments(comments_forest: CommentForest) -> bool:
    return any(isinstance(comment, praw.models.MoreComments) for comment in comments_forest)


def _expand_more_comments(comments_forest: CommentForest) -> None:
    """Fetch MoreComments batches until none remain or expansion stalls."""
    while _has_more_comments(comments_forest):
        previous_len = len(comments_forest)
        comments_forest.replace_more(limit=32)
        if len(comments_forest) == previous_len:
            break


def _walk_comments_in_order(
    comments_forest: CommentForest,
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
) -> list[dict[str, Any]]:
    """Collect up to max_comments eligible comments for a submission."""
    rows: list[dict[str, Any]] = []
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


@dataclass(frozen=True)
class RedditTask:
    task_id: str
    subreddit: str


def _normalize_subreddit_key(subreddit: str) -> str:
    return subreddit.removeprefix("r/").lower()


def build_sync_tasks(ingestion_params: dict[str, Any]) -> list[RedditTask]:
    """Return sync tasks keyed by subreddit for checkpointing."""
    subreddits = ingestion_params.get("subreddits")
    if not isinstance(subreddits, list) or not subreddits:
        raise ValueError("ingestion_params must include 'subreddits' as a non-empty list")

    items: list[RedditTask] = []
    for subreddit in subreddits:
        if not isinstance(subreddit, str) or not subreddit.strip():
            raise ValueError("ingestion_params.subreddits entries must be non-empty strings")
        task_id = _normalize_subreddit_key(subreddit)
        items.append(RedditTask(task_id=task_id, subreddit=subreddit.strip()))
    return items


def _resolve_listing_time_filter(ingestion_params: dict[str, Any], listing: str) -> str | None:
    raw = ingestion_params.get("listing_time_filter")
    if raw is None:
        return None
    if listing != "top":
        raise ValueError("ingestion_params.listing_time_filter is only valid when listing is 'top'")
    time_filter = str(raw)
    if time_filter not in VALID_LISTING_TIME_FILTERS:
        raise ValueError(f"Unsupported ingestion_params.listing_time_filter value: {time_filter!r}")
    return time_filter


def _get_subreddit_listing(
    subreddit_obj: praw.models.Subreddit,
    listing: str,
    limit: int,
    *,
    time_filter: str | None = None,
) -> list[praw.models.Submission]:
    if listing == "new":
        return list(subreddit_obj.new(limit=limit))
    if listing == "top":
        kwargs: dict[str, Any] = {"limit": limit}
        if time_filter is not None:
            kwargs["time_filter"] = time_filter
        return list(subreddit_obj.top(**kwargs))
    if listing == "rising":
        return list(subreddit_obj.rising(limit=limit))
    if listing != "hot":
        raise ValueError(f"Unsupported ingestion_params.listing value: {listing!r}")
    return list(subreddit_obj.hot(limit=limit))


@retry_reddit_request()
def _fetch_subreddit_page(
    reddit: praw.Reddit,
    subreddit: str,
    listing: str,
    limit: int,
    *,
    time_filter: str | None = None,
) -> list[praw.models.Submission]:
    return _get_subreddit_listing(
        reddit.subreddit(subreddit), listing, limit, time_filter=time_filter
    )


def fetch_records_for_subreddit(
    reddit: praw.Reddit,
    ingestion_params: dict[str, Any],
    subreddit: str,
    *,
    sync_timestamp: str,
    include_posts: bool,
    include_comments: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Fetch posts and/or comments for a single subreddit."""
    limit = int(ingestion_params["limit_per_subreddit"])
    listing = str(ingestion_params.get("listing", DEFAULT_LISTING))
    listing_time_filter = _resolve_listing_time_filter(ingestion_params, listing)
    comments_per_post = int(ingestion_params.get("comments_per_post", 100))
    min_comment_body_length = int(ingestion_params.get("min_comment_body_length", 30))

    try:
        submissions = _fetch_subreddit_page(
            reddit, subreddit, listing, limit, time_filter=listing_time_filter
        )
    except prawcore.exceptions.NotFound:
        logger.warning("Subreddit not found: %s", subreddit)
        return (
            [],
            [],
            {
                "subreddit": subreddit,
                "listing": listing,
                "listing_time_filter": listing_time_filter,
                "limit_per_subreddit": limit,
                "posts_collected": 0,
                "comments_collected": 0,
            },
        )

    post_rows: list[dict[str, Any]] = []
    comment_rows: list[dict[str, Any]] = []

    for post in submissions:
        if include_posts:
            post_rows.append(submission_to_row(post, sync_timestamp))

        if include_comments:
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

    stats = {
        "subreddit": subreddit,
        "listing": listing,
        "listing_time_filter": listing_time_filter,
        "limit_per_subreddit": limit,
        "posts_collected": len(post_rows),
        "comments_collected": len(comment_rows),
    }
    return post_rows, comment_rows, stats


def _initial_task_progress(task: RedditTask) -> dict[str, Any]:
    return {
        "status": TaskStatus.PENDING.value,
        "kind": "reddit",
        "subreddit": task.subreddit,
        "posts_collected": 0,
        "comments_collected": 0,
        "last_error": None,
    }


def init_sync_metadata(
    config: dict[str, Any],
    config_path: Path,
    sync_timestamp: str,
    sync_tasks: list[RedditTask],
) -> dict[str, Any]:
    return build_base_sync_metadata(
        config,
        config_path,
        sync_timestamp,
        sync_tasks,
        task_progress_builder=_initial_task_progress,
        extra_fields={"post_row_count": 0},
    )


def _open_reddit_dedupe_sessions(
    comment_storage: RedditStorageManager,
    post_storage: RedditStorageManager,
    output_dir: Path,
    ingestion_params: dict[str, Any],
    *,
    include_comments: bool,
    include_posts: bool,
    comments_csv: str,
    posts_csv: str,
) -> tuple[DedupeSession | None, DedupeSession | None]:
    comment_dedupe_session: DedupeSession | None = None
    post_dedupe_session: DedupeSession | None = None
    if include_comments:
        comment_dedupe_session = DedupeSession(
            DedupeConfig(id_column="comment_fullname", filename=comments_csv)
        )
        comment_dedupe_session.warm(comment_storage, output_dir)
    if include_posts:
        post_dedupe_session = DedupeSession(
            DedupeConfig(id_column="reddit_fullname", filename=posts_csv)
        )
        post_dedupe_session.warm(post_storage, output_dir)
    return comment_dedupe_session, post_dedupe_session


def _append_subreddit_deduped_rows(
    comment_storage: RedditStorageManager,
    post_storage: RedditStorageManager,
    output_dir: Path,
    metadata: dict[str, Any],
    post_rows: list[dict[str, Any]],
    comment_rows: list[dict[str, Any]],
    *,
    include_comments: bool,
    include_posts: bool,
    comment_dedupe_session: DedupeSession | None,
    post_dedupe_session: DedupeSession | None,
    comments_csv: str,
    posts_csv: str,
) -> tuple[int, int]:
    if include_posts and post_rows and post_dedupe_session is not None:
        post_result = post_storage.append_deduped_records(
            post_rows,
            output_dir,
            dedupe_session=post_dedupe_session,
            filename=posts_csv,
        )
        metadata["posts_skipped_as_duplicates"] = (
            int(metadata.get("posts_skipped_as_duplicates", 0)) + post_result.skipped
        )

    if include_comments and comment_rows and comment_dedupe_session is not None:
        comment_result = comment_storage.append_deduped_records(
            comment_rows,
            output_dir,
            dedupe_session=comment_dedupe_session,
            filename=comments_csv,
        )
        metadata["comments_skipped_as_duplicates"] = (
            int(metadata.get("comments_skipped_as_duplicates", 0)) + comment_result.skipped
        )

    comment_count = (
        len(comment_dedupe_session.seen_ids)
        if include_comments and comment_dedupe_session is not None
        else 0
    )
    post_count = (
        len(post_dedupe_session.seen_ids)
        if include_posts and post_dedupe_session is not None
        else 0
    )
    metadata["row_count"] = comment_count
    metadata["post_row_count"] = post_count
    return comment_count, post_count


def run_sync_tasks(
    reddit: praw.Reddit,
    ingestion_params: dict[str, Any],
    output_dir: Path,
    comment_storage: RedditStorageManager,
    post_storage: RedditStorageManager,
    metadata: dict[str, Any],
    sync_tasks: list[RedditTask],
    *,
    include_comments: bool,
    include_posts: bool,
) -> None:
    max_rows_int = parse_max_rows(ingestion_params)
    sync_timestamp = str(metadata["sync_timestamp"])
    comments_csv = record_type_to_filename(COMMENTS_RECORD_TYPE)
    posts_csv = record_type_to_filename(POSTS_RECORD_TYPE)

    comment_dedupe_session, post_dedupe_session = _open_reddit_dedupe_sessions(
        comment_storage,
        post_storage,
        output_dir,
        ingestion_params,
        include_comments=include_comments,
        include_posts=include_posts,
        comments_csv=comments_csv,
        posts_csv=posts_csv,
    )
    if comment_dedupe_session or post_dedupe_session:
        prior_comment_count = len(comment_dedupe_session.seen_ids) if comment_dedupe_session else 0
        prior_post_count = len(post_dedupe_session.seen_ids) if post_dedupe_session else 0
        print(
            f"sync_records: loaded {prior_comment_count} prior comment IDs, "
            f"{prior_post_count} prior post IDs for dedupe"
        )

    def process_task(task: RedditTask, entry: dict[str, Any]) -> None:
        mark_task_in_progress(entry, comment_storage, output_dir, metadata)

        try:
            post_rows, comment_rows, stats = fetch_records_for_subreddit(
                reddit,
                ingestion_params,
                task.subreddit,
                sync_timestamp=sync_timestamp,
                include_posts=include_posts,
                include_comments=include_comments,
            )
        except Exception as exc:  # noqa: BLE001 — record and continue
            mark_task_failed(entry, exc, task.task_id, comment_storage, output_dir, metadata)
            return

        comment_count, post_count = _append_subreddit_deduped_rows(
            comment_storage,
            post_storage,
            output_dir,
            metadata,
            post_rows,
            comment_rows,
            include_comments=include_comments,
            include_posts=include_posts,
            comment_dedupe_session=comment_dedupe_session,
            post_dedupe_session=post_dedupe_session,
            comments_csv=comments_csv,
            posts_csv=posts_csv,
        )
        mark_task_completed(
            entry,
            comment_storage,
            output_dir,
            metadata,
            entry_updates={
                "posts_collected": stats["posts_collected"],
                "comments_collected": stats["comments_collected"],
            },
        )

        print(
            f"sync_records: {task.task_id} -> "
            f"{stats['comments_collected']} comments, {stats['posts_collected']} posts "
            f"(total comments={comment_count}, total posts={post_count})"
        )

    run_checkpointed_sync(
        sync_tasks,
        metadata,
        comment_storage,
        output_dir,
        max_rows_int=max_rows_int,
        tqdm_desc="Syncing subreddits",
        process_task=process_task,
    )


load_config = load_yaml_config


def sync_records(
    config_path: Path,
    *,
    resume: bool = False,
    run_dir_name: str | None = None,
) -> Path:
    """Fetch Reddit records per config and write raw CSV + metadata."""
    config = load_config(config_path)
    dataset_id = require_dataset_id(config, platform="reddit")
    comment_storage = RedditStorageManager(StorageStage.RAW, dataset_id)
    post_storage = comment_storage.post_storage()

    ensure_dataset_manifest(
        comment_storage,
        "reddit",
        dataset_id,
        config,
        config_path,
    )

    ingestion_params = config["ingestion_params"]
    sync_tasks = build_sync_tasks(ingestion_params)
    record_types: list[str] = config["record_types"]
    include_comments = COMMENTS_RECORD_TYPE in record_types
    include_posts = POSTS_RECORD_TYPE in record_types

    if not include_comments and not include_posts:
        raise ValueError(f"Unsupported record types for checkpoint sync: {record_types}")

    reddit = init_reddit_client()

    output_dir, metadata = prepare_sync_run(
        comment_storage,
        sync_tasks,
        resume=resume,
        run_dir_name=run_dir_name,
        init_metadata_fn=lambda ts: init_sync_metadata(config, config_path, ts, sync_tasks),
        entity_label="subreddits",
    )

    run_sync_tasks(
        reddit,
        ingestion_params,
        output_dir,
        comment_storage,
        post_storage,
        metadata,
        sync_tasks,
        include_comments=include_comments,
        include_posts=include_posts,
    )

    print(
        f"sync_records: wrote {metadata['row_count']} comments and "
        f"{metadata['post_row_count']} posts to {output_dir} "
        f"(status={metadata['sync_status']})"
    )
    return output_dir


def main() -> None:
    run_sync_cli(
        sync_records_fn=sync_records,
        config_help=(
            "Ingestion YAML path relative to the repo root "
            "(e.g. data_platform/ingestion/configs/reddit/mirrorview.yaml)"
        ),
    )


if __name__ == "__main__":
    main()
