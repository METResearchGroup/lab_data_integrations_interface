"""Sync Reddit comments from YAML config to raw CSV storage.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/ingestion/sync_reddit.py

    PYTHONPATH=. uv run python data_platform/ingestion/sync_reddit.py --config mirrorview.yaml

Resume the latest in-progress run for a dataset:

    PYTHONPATH=. uv run python data_platform/ingestion/sync_reddit.py \\
        --config mirrorview.yaml --resume

Resume a specific raw run timestamp:

    PYTHONPATH=. uv run python data_platform/ingestion/sync_reddit.py \\
        --config mirrorview.yaml --resume --run-dir 2026_05_30-12:00:00

Ingestion YAML must include `dataset_id` (e.g. reddit_<uuid>).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import praw
import praw.models
import prawcore.exceptions

from data_platform.ingestion.dedupe import append_deduped_rows, load_prior_seen_ids
from data_platform.ingestion.reddit_retry import retry_reddit_request
from data_platform.ingestion.sync_checkpoint import (
    TaskStatus,
    build_base_sync_metadata,
    ensure_dataset_manifest,
    flush_run_metadata,
    mark_task_failed,
    mark_task_in_progress,
    parse_max_rows,
    prepare_sync_run,
    record_type_to_filename,
    require_dataset_id,
    run_checkpointed_sync,
    run_sync_cli,
)
from data_platform.utils.config_paths import load_yaml_config
from data_platform.utils.storage import RedditStorageManager
from experiments.reddit_fetch_data_2026_05_23.reddit_client import (
    fetch_post_comments,
    init_reddit,
    submission_to_row,
)

CONFIGS_DIR = Path(__file__).resolve().parent / "configs/reddit"
DEFAULT_CONFIG = CONFIGS_DIR / "default.yaml"
REPO_ROOT = Path(__file__).resolve().parents[2]

COMMENTS_RECORD_TYPE = "reddit.comment"
POSTS_RECORD_TYPE = "reddit.post"
DEFAULT_LISTING = "hot"
VALID_LISTING_TIME_FILTERS = frozenset({"all", "day", "hour", "month", "week", "year"})

logger = logging.getLogger(__name__)


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
            post_rows.append(submission_to_row(post, sync_timestamp))  # type: ignore[arg-type]

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


def _count_seen_rows(
    comment_storage: RedditStorageManager,
    post_storage: RedditStorageManager,
    output_dir: Path,
    *,
    include_comments: bool,
    include_posts: bool,
) -> tuple[int, int]:
    comments_csv = record_type_to_filename(COMMENTS_RECORD_TYPE)
    posts_csv = record_type_to_filename(POSTS_RECORD_TYPE)
    comment_count = (
        len(comment_storage.load_seen_ids(output_dir, "comment_fullname", filename=comments_csv))
        if include_comments
        else 0
    )
    post_count = (
        len(post_storage.load_seen_ids(output_dir, "reddit_fullname", filename=posts_csv))
        if include_posts
        else 0
    )
    return comment_count, post_count


def _append_fetched_subreddit_rows(
    comment_storage: RedditStorageManager,
    post_storage: RedditStorageManager,
    output_dir: Path,
    post_rows: list[dict[str, Any]],
    comment_rows: list[dict[str, Any]],
    *,
    include_comments: bool,
    include_posts: bool,
    prior_comment_ids: set[str] | None = None,
    prior_post_ids: set[str] | None = None,
) -> tuple[int, int]:
    comments_csv = record_type_to_filename(COMMENTS_RECORD_TYPE)
    posts_csv = record_type_to_filename(POSTS_RECORD_TYPE)
    comments_skipped = 0
    posts_skipped = 0

    if include_posts and post_rows:
        _, posts_skipped = append_deduped_rows(
            post_storage,
            output_dir,
            post_rows,
            "reddit_fullname",
            prior_ids=prior_post_ids or set(),
            filename=posts_csv,
        )

    if include_comments and comment_rows:
        _, comments_skipped = append_deduped_rows(
            comment_storage,
            output_dir,
            comment_rows,
            "comment_fullname",
            prior_ids=prior_comment_ids or set(),
            filename=comments_csv,
        )

    return comments_skipped, posts_skipped


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

    prior_comment_ids: set[str] = set()
    prior_post_ids: set[str] = set()
    if include_comments:
        prior_comment_ids = load_prior_seen_ids(
            comment_storage,
            output_dir,
            ingestion_params,
            "comment_fullname",
            filename=comments_csv,
            same_dataset_flag="dedupe_comments_from_prior_raw_runs",
        )
    if include_posts:
        prior_post_ids = load_prior_seen_ids(
            post_storage,
            output_dir,
            ingestion_params,
            "reddit_fullname",
            filename=posts_csv,
            same_dataset_flag="dedupe_comments_from_prior_raw_runs",
        )
    if prior_comment_ids or prior_post_ids:
        print(
            f"sync_records: loaded {len(prior_comment_ids)} prior comment IDs, "
            f"{len(prior_post_ids)} prior post IDs for dedupe"
        )
    comments_skipped = int(metadata.get("comments_skipped_as_duplicates", 0))
    posts_skipped = int(metadata.get("posts_skipped_as_duplicates", 0))

    def process_task(task: RedditTask, entry: dict[str, Any]) -> None:
        nonlocal comments_skipped, posts_skipped

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

        comments_skipped_delta, posts_skipped_delta = _append_fetched_subreddit_rows(
            comment_storage,
            post_storage,
            output_dir,
            post_rows,
            comment_rows,
            include_comments=include_comments,
            include_posts=include_posts,
            prior_comment_ids=prior_comment_ids,
            prior_post_ids=prior_post_ids,
        )
        comments_skipped += comments_skipped_delta
        posts_skipped += posts_skipped_delta
        metadata["comments_skipped_as_duplicates"] = comments_skipped
        metadata["posts_skipped_as_duplicates"] = posts_skipped

        comment_count, post_count = _count_seen_rows(
            comment_storage,
            post_storage,
            output_dir,
            include_comments=include_comments,
            include_posts=include_posts,
        )
        metadata["row_count"] = comment_count
        metadata["post_row_count"] = post_count
        entry["status"] = TaskStatus.COMPLETED.value
        entry["posts_collected"] = stats["posts_collected"]
        entry["comments_collected"] = stats["comments_collected"]
        entry["last_error"] = None
        flush_run_metadata(comment_storage, output_dir, metadata)

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
    config_path: Path = DEFAULT_CONFIG,
    *,
    resume: bool = False,
    run_dir_name: str | None = None,
) -> Path:
    """Fetch Reddit records per config and write raw CSV + metadata."""
    config = load_config(config_path)
    dataset_id = require_dataset_id(config, platform="reddit")
    comment_storage = RedditStorageManager("raw", dataset_id)
    post_storage = comment_storage.post_storage()

    ensure_dataset_manifest(
        comment_storage,
        "reddit",
        dataset_id,
        config,
        config_path,
        repo_root=REPO_ROOT,
    )

    ingestion_params = config["ingestion_params"]
    sync_tasks = build_sync_tasks(ingestion_params)
    record_types: list[str] = config["record_types"]
    include_comments = COMMENTS_RECORD_TYPE in record_types
    include_posts = POSTS_RECORD_TYPE in record_types

    if not include_comments and not include_posts:
        raise ValueError(f"Unsupported record types for checkpoint sync: {record_types}")

    reddit = init_reddit()

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
        configs_dir=CONFIGS_DIR,
        default_config=DEFAULT_CONFIG,
        sync_records_fn=sync_records,
        config_help="YAML config path or filename under configs/reddit/ (e.g. mirrorview.yaml)",
    )


if __name__ == "__main__":
    main()
