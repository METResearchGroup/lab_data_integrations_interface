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
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import praw
import praw.models
import prawcore.exceptions
import typer
from tqdm import tqdm

from data_platform.ingestion.reddit_retry import retry_reddit_request
from data_platform.ingestion.sync_checkpoint import (
    flush_sync_metadata,
    init_sync_metadata_base,
    mark_remaining_skipped,
    sync_status_done,
)
from data_platform.ingestion.sync_runner import (
    ensure_dataset_manifest,
    make_sync_main,
    prepare_sync_run,
    require_dataset_id,
    validate_run_dir_option,
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

COMMENTS_RECORD_TYPE = "reddit.comment"
POSTS_RECORD_TYPE = "reddit.post"
COMMENTS_CSV = "comments.csv"
POSTS_CSV = "posts.csv"
DEFAULT_LISTING = "hot"
VALID_LISTING_TIME_FILTERS = frozenset({"all", "day", "hour", "month", "week", "year"})

SubredditStatus = Literal["pending", "in_progress", "completed", "failed", "skipped"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FetchWorkItem:
    subreddit: str
    work_item_key: str


def _record_type_to_filename(record_type: str) -> str:
    if record_type == COMMENTS_RECORD_TYPE:
        return COMMENTS_CSV
    if record_type == POSTS_RECORD_TYPE:
        return POSTS_CSV
    return f"{record_type.rsplit('.', 1)[-1]}.csv"


def _normalize_subreddit_key(subreddit: str) -> str:
    return subreddit.removeprefix("r/").lower()


def iter_fetch_work_items(fetch: dict[str, Any]) -> list[FetchWorkItem]:
    """Return work items keyed by subreddit for checkpointing."""
    subreddits = fetch.get("subreddits")
    if not isinstance(subreddits, list) or not subreddits:
        raise ValueError("fetch config must include 'subreddits' as a non-empty list")

    items: list[FetchWorkItem] = []
    for subreddit in subreddits:
        if not isinstance(subreddit, str) or not subreddit.strip():
            raise ValueError("fetch.subreddits entries must be non-empty strings")
        work_item_key = _normalize_subreddit_key(subreddit)
        items.append(FetchWorkItem(subreddit=subreddit.strip(), work_item_key=work_item_key))
    return items


def _resolve_listing_time_filter(fetch: dict[str, Any], listing: str) -> str | None:
    raw = fetch.get("listing_time_filter")
    if raw is None:
        return None
    if listing != "top":
        raise ValueError("fetch.listing_time_filter is only valid when listing is 'top'")
    time_filter = str(raw)
    if time_filter not in VALID_LISTING_TIME_FILTERS:
        raise ValueError(f"Unsupported fetch.listing_time_filter value: {time_filter!r}")
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
        raise ValueError(f"Unsupported fetch.listing value: {listing!r}")
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
    fetch: dict[str, Any],
    subreddit: str,
    *,
    sync_timestamp: str,
    include_posts: bool,
    include_comments: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Fetch posts and/or comments for a single subreddit."""
    limit = int(fetch["limit_per_subreddit"])
    listing = str(fetch.get("listing", DEFAULT_LISTING))
    listing_time_filter = _resolve_listing_time_filter(fetch, listing)
    comments_per_post = int(fetch.get("comments_per_post", 100))
    min_comment_body_length = int(fetch.get("min_comment_body_length", 30))

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


def _subreddit_entry(item: FetchWorkItem) -> dict[str, Any]:
    return {
        "status": "pending",
        "subreddit": item.subreddit,
        "posts_collected": 0,
        "comments_collected": 0,
        "last_error": None,
    }


def init_sync_metadata(
    config: dict[str, Any],
    config_path: Path,
    sync_timestamp: str,
    work_items: list[FetchWorkItem],
) -> dict[str, Any]:
    dataset_id = require_dataset_id(config, hint="reddit_<uuid>")
    return init_sync_metadata_base(
        config,
        config_path,
        sync_timestamp,
        dataset_id=dataset_id,
        metadata_bucket="subreddits",
        entries={item.work_item_key: _subreddit_entry(item) for item in work_items},
        extra={"post_row_count": 0},
    )


def _count_seen_rows(
    comment_storage: RedditStorageManager,
    post_storage: RedditStorageManager,
    output_dir: Path,
    *,
    include_comments: bool,
    include_posts: bool,
) -> tuple[int, int]:
    comment_count = (
        len(comment_storage.load_seen_ids(output_dir, "comment_fullname", filename=COMMENTS_CSV))
        if include_comments
        else 0
    )
    post_count = (
        len(post_storage.load_seen_ids(output_dir, "reddit_fullname", filename=POSTS_CSV))
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
) -> int:
    comments_skipped = 0
    if include_posts and post_rows:
        seen_posts = post_storage.load_seen_ids(output_dir, "reddit_fullname", filename=POSTS_CSV)
        new_posts = [row for row in post_rows if row["reddit_fullname"] not in seen_posts]
        if new_posts:
            post_storage.append_records(new_posts, output_dir, filename=POSTS_CSV)

    if include_comments and comment_rows:
        seen_comments = (prior_comment_ids or set()) | comment_storage.load_seen_ids(
            output_dir, "comment_fullname", filename=COMMENTS_CSV
        )
        new_comments = [row for row in comment_rows if row["comment_fullname"] not in seen_comments]
        comments_skipped = len(comment_rows) - len(new_comments)
        if new_comments:
            comment_storage.append_records(new_comments, output_dir, filename=COMMENTS_CSV)
    return comments_skipped


def _stop_if_at_max_rows(
    max_rows_int: int | None,
    metadata: dict[str, Any],
    storage: RedditStorageManager,
    output_dir: Path,
) -> bool:
    if max_rows_int is not None and metadata["row_count"] >= max_rows_int:
        mark_remaining_skipped(metadata, metadata_bucket="subreddits")
        flush_sync_metadata(storage, output_dir, metadata)
        return True
    return False


def run_subreddit_sync_loop(
    reddit: praw.Reddit,
    fetch: dict[str, Any],
    output_dir: Path,
    comment_storage: RedditStorageManager,
    post_storage: RedditStorageManager,
    metadata: dict[str, Any],
    work_items: list[FetchWorkItem],
    *,
    include_comments: bool,
    include_posts: bool,
) -> None:
    max_rows = fetch.get("max_rows")
    max_rows_int = int(max_rows) if max_rows is not None else None
    sync_timestamp = str(metadata["sync_timestamp"])
    prior_comment_ids: set[str] = set()
    if include_comments and fetch.get("dedupe_comments_from_prior_raw_runs"):
        prior_comment_ids = comment_storage.load_seen_ids_from_prior_runs(
            output_dir, "comment_fullname", filename=COMMENTS_CSV
        )
    comments_skipped = int(metadata.get("comments_skipped_as_duplicates", 0))

    for item in tqdm(
        work_items,
        desc="Syncing subreddits",
        disable=not sys.stderr.isatty(),
    ):
        entry = metadata["subreddits"][item.work_item_key]
        status = entry["status"]
        if status in ("completed", "skipped"):
            continue

        if _stop_if_at_max_rows(max_rows_int, metadata, comment_storage, output_dir):
            break

        entry["status"] = "in_progress"
        entry["last_error"] = None
        flush_sync_metadata(comment_storage, output_dir, metadata)

        try:
            post_rows, comment_rows, stats = fetch_records_for_subreddit(
                reddit,
                fetch,
                item.subreddit,
                sync_timestamp=sync_timestamp,
                include_posts=include_posts,
                include_comments=include_comments,
            )
        except Exception as exc:  # noqa: BLE001 — record and continue
            entry["status"] = "failed"
            entry["last_error"] = str(exc)
            flush_sync_metadata(comment_storage, output_dir, metadata)
            print(f"sync_records: {item.work_item_key} failed: {exc}")
            continue

        comments_skipped += _append_fetched_subreddit_rows(
            comment_storage,
            post_storage,
            output_dir,
            post_rows,
            comment_rows,
            include_comments=include_comments,
            include_posts=include_posts,
            prior_comment_ids=prior_comment_ids,
        )
        metadata["comments_skipped_as_duplicates"] = comments_skipped

        comment_count, post_count = _count_seen_rows(
            comment_storage,
            post_storage,
            output_dir,
            include_comments=include_comments,
            include_posts=include_posts,
        )
        metadata["row_count"] = comment_count
        metadata["post_row_count"] = post_count
        entry["status"] = "completed"
        entry["posts_collected"] = stats["posts_collected"]
        entry["comments_collected"] = stats["comments_collected"]
        entry["last_error"] = None
        flush_sync_metadata(comment_storage, output_dir, metadata)

        print(
            f"sync_records: {item.work_item_key} -> "
            f"{stats['comments_collected']} comments, {stats['posts_collected']} posts "
            f"(total comments={comment_count}, total posts={post_count})"
        )

        if _stop_if_at_max_rows(max_rows_int, metadata, comment_storage, output_dir):
            break

    metadata["sync_status"] = sync_status_done(metadata, metadata_bucket="subreddits")
    flush_sync_metadata(comment_storage, output_dir, metadata)


load_config = load_yaml_config


def sync_records(
    config_path: Path = DEFAULT_CONFIG,
    *,
    resume: bool = False,
    run_dir_name: str | None = None,
) -> Path:
    """Fetch Reddit records per config and write raw CSV + metadata."""
    validate_run_dir_option(run_dir_name, resume=resume)

    config = load_config(config_path)
    dataset_id = require_dataset_id(config, hint="reddit_<uuid>")
    comment_storage = RedditStorageManager("raw", dataset_id)
    post_storage = comment_storage.post_storage()
    ensure_dataset_manifest("reddit", comment_storage, config, config_path)

    work_items = iter_fetch_work_items(config["fetch"])
    record_types: list[str] = config["record_types"]
    include_comments = COMMENTS_RECORD_TYPE in record_types
    include_posts = POSTS_RECORD_TYPE in record_types

    if not include_comments and not include_posts:
        raise ValueError(f"Unsupported record types for checkpoint sync: {record_types}")

    prepared = prepare_sync_run(
        comment_storage,
        config,
        config_path,
        work_items,
        resume=resume,
        run_dir_name=run_dir_name,
        metadata_bucket="subreddits",
        entity_label="subreddits",
        init_sync_metadata=init_sync_metadata,
    )

    run_subreddit_sync_loop(
        init_reddit(),
        prepared.fetch,
        prepared.output_dir,
        comment_storage,
        post_storage,
        prepared.metadata,
        prepared.work_items,
        include_comments=include_comments,
        include_posts=include_posts,
    )

    print(
        f"sync_records: wrote {prepared.metadata['row_count']} comments and "
        f"{prepared.metadata['post_row_count']} posts to {prepared.output_dir} "
        f"(status={prepared.metadata['sync_status']})"
    )
    return prepared.output_dir


main = make_sync_main(
    sync_records=sync_records,
    configs_dir=CONFIGS_DIR,
    default_config=DEFAULT_CONFIG,
    config_help_subdir="reddit",
)


if __name__ == "__main__":
    typer.run(main)
