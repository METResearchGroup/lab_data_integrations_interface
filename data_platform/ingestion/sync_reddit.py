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
from typing import Any

import praw
import praw.models
import prawcore.exceptions
import typer
from tqdm import tqdm

from data_platform.ingestion.dedupe import load_prior_seen_ids
from data_platform.ingestion.reddit_retry import retry_reddit_request
from data_platform.ingestion.sync_checkpoint import (
    SyncStatus,
    TaskStatus,
    get_task_progress,
    mark_remaining_tasks_skipped,
    sync_status_from_tasks,
    validate_tasks_for_resume,
)
from data_platform.utils.config_paths import load_yaml_config, resolve_config_path
from data_platform.utils.dataset import validate_dataset_id, write_dataset_manifest
from data_platform.utils.storage import RedditStorageManager
from experiments.reddit_fetch_data_2026_05_23.reddit_client import (
    fetch_post_comments,
    init_reddit,
    submission_to_row,
)
from lib.timestamp_utils import get_current_timestamp

CONFIGS_DIR = Path(__file__).resolve().parent / "configs/reddit"
DEFAULT_CONFIG = CONFIGS_DIR / "default.yaml"

COMMENTS_RECORD_TYPE = "reddit.comment"
POSTS_RECORD_TYPE = "reddit.post"
COMMENTS_CSV = "comments.csv"
POSTS_CSV = "posts.csv"
DEFAULT_LISTING = "hot"
VALID_LISTING_TIME_FILTERS = frozenset({"all", "day", "hour", "month", "week", "year"})

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RedditTask:
    task_id: str
    subreddit: str


def _record_type_to_filename(record_type: str) -> str:
    if record_type == COMMENTS_RECORD_TYPE:
        return COMMENTS_CSV
    if record_type == POSTS_RECORD_TYPE:
        return POSTS_CSV
    return f"{record_type.rsplit('.', 1)[-1]}.csv"


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
    dataset_id = _require_dataset_id(config)
    return {
        "sync_status": SyncStatus.IN_PROGRESS.value,
        "dataset_id": dataset_id,
        "name": config["name"],
        "description": config["description"],
        "date": config["date"],
        "sync_timestamp": sync_timestamp,
        "ingestion_config": config_path.name,
        "record_types": config["record_types"],
        "ingestion_params": config["ingestion_params"],
        "row_count": 0,
        "post_row_count": 0,
        "tasks": {task.task_id: _initial_task_progress(task) for task in sync_tasks},
    }


def _flush_metadata(storage: RedditStorageManager, run_dir: Path, metadata: dict[str, Any]) -> None:
    storage.write_run_metadata_atomic(run_dir, metadata)


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
    prior_post_ids: set[str] | None = None,
) -> tuple[int, int]:
    comments_skipped = 0
    posts_skipped = 0
    if include_posts and post_rows:
        seen_posts = (prior_post_ids or set()) | post_storage.load_seen_ids(
            output_dir, "reddit_fullname", filename=POSTS_CSV
        )
        new_posts = [row for row in post_rows if row["reddit_fullname"] not in seen_posts]
        posts_skipped = len(post_rows) - len(new_posts)
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
    return comments_skipped, posts_skipped


def _stop_if_at_max_rows(
    max_rows_int: int | None,
    metadata: dict[str, Any],
    storage: RedditStorageManager,
    output_dir: Path,
) -> bool:
    if max_rows_int is not None and metadata["row_count"] >= max_rows_int:
        mark_remaining_tasks_skipped(get_task_progress(metadata))
        _flush_metadata(storage, output_dir, metadata)
        return True
    return False


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
    max_rows = ingestion_params.get("max_rows")
    max_rows_int = int(max_rows) if max_rows is not None else None
    sync_timestamp = str(metadata["sync_timestamp"])
    prior_comment_ids: set[str] = set()
    prior_post_ids: set[str] = set()
    if include_comments:
        prior_comment_ids = load_prior_seen_ids(
            comment_storage,
            output_dir,
            ingestion_params,
            "comment_fullname",
            filename=COMMENTS_CSV,
            same_dataset_flag="dedupe_comments_from_prior_raw_runs",
        )
    if include_posts:
        prior_post_ids = load_prior_seen_ids(
            post_storage,
            output_dir,
            ingestion_params,
            "reddit_fullname",
            filename=POSTS_CSV,
            same_dataset_flag="dedupe_comments_from_prior_raw_runs",
        )
    if prior_comment_ids or prior_post_ids:
        print(
            f"sync_records: loaded {len(prior_comment_ids)} prior comment IDs, "
            f"{len(prior_post_ids)} prior post IDs for dedupe"
        )
    comments_skipped = int(metadata.get("comments_skipped_as_duplicates", 0))
    posts_skipped = int(metadata.get("posts_skipped_as_duplicates", 0))
    progress = get_task_progress(metadata)

    for task in tqdm(
        sync_tasks,
        desc="Syncing subreddits",
        disable=not sys.stderr.isatty(),
    ):
        entry = progress[task.task_id]
        status = entry["status"]
        if status in (TaskStatus.COMPLETED.value, TaskStatus.SKIPPED.value):
            continue

        if _stop_if_at_max_rows(max_rows_int, metadata, comment_storage, output_dir):
            break

        entry["status"] = TaskStatus.IN_PROGRESS.value
        entry["last_error"] = None
        _flush_metadata(comment_storage, output_dir, metadata)

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
            entry["status"] = TaskStatus.FAILED.value
            entry["last_error"] = str(exc)
            _flush_metadata(comment_storage, output_dir, metadata)
            print(f"sync_records: {task.task_id} failed: {exc}")
            continue

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
        _flush_metadata(comment_storage, output_dir, metadata)

        print(
            f"sync_records: {task.task_id} -> "
            f"{stats['comments_collected']} comments, {stats['posts_collected']} posts "
            f"(total comments={comment_count}, total posts={post_count})"
        )

        if _stop_if_at_max_rows(max_rows_int, metadata, comment_storage, output_dir):
            break

    metadata["sync_status"] = sync_status_from_tasks(progress).value
    _flush_metadata(comment_storage, output_dir, metadata)


def find_resume_run_dir(
    storage: RedditStorageManager,
    *,
    run_dir_name: str | None,
) -> Path:
    if run_dir_name is not None:
        run_dir = storage.root_dir / run_dir_name
        if not run_dir.is_dir():
            raise FileNotFoundError(f"Run directory not found: {run_dir}")
        return run_dir

    if not storage.root_dir.exists():
        raise FileNotFoundError(f"No raw runs found under {storage.root_dir}")

    candidates: list[tuple[str, Path]] = []
    for path in storage.root_dir.iterdir():
        if not path.is_dir():
            continue
        metadata_path = path / "metadata.json"
        if not metadata_path.exists():
            continue
        metadata = storage.load_run_metadata(path)
        if metadata.get("sync_status") == SyncStatus.IN_PROGRESS.value:
            candidates.append((path.name, path))

    if not candidates:
        raise FileNotFoundError(
            f"No in-progress raw run found under {storage.root_dir}. "
            "Start a new sync or pass --run-dir."
        )
    return max(candidates, key=lambda item: item[0])[1]


load_config = load_yaml_config


def _require_dataset_id(config: dict[str, Any]) -> str:
    raw = config.get("dataset_id")
    if not raw:
        raise ValueError("ingestion config must include dataset_id (reddit_<uuid>)")
    return validate_dataset_id(str(raw))


def sync_records(
    config_path: Path = DEFAULT_CONFIG,
    *,
    resume: bool = False,
    run_dir_name: str | None = None,
) -> Path:
    """Fetch Reddit records per config and write raw CSV + metadata."""
    if run_dir_name is not None and not resume:
        raise ValueError("--run-dir requires --resume")

    config = load_config(config_path)
    dataset_id = _require_dataset_id(config)
    comment_storage = RedditStorageManager("raw", dataset_id)
    post_storage = comment_storage.post_storage()

    manifest_path = comment_storage.root_dir.parent / "dataset.json"
    if not manifest_path.exists():
        write_dataset_manifest(
            "reddit",
            dataset_id,
            name=str(config["name"]),
            ingestion_config=str(config_path.relative_to(Path(__file__).resolve().parents[2])),
        )

    ingestion_params = config["ingestion_params"]
    sync_tasks = build_sync_tasks(ingestion_params)
    record_types: list[str] = config["record_types"]
    include_comments = COMMENTS_RECORD_TYPE in record_types
    include_posts = POSTS_RECORD_TYPE in record_types

    if not include_comments and not include_posts:
        raise ValueError(f"Unsupported record types for checkpoint sync: {record_types}")

    reddit = init_reddit()

    if resume:
        output_dir = find_resume_run_dir(comment_storage, run_dir_name=run_dir_name)
        metadata = comment_storage.load_run_metadata(output_dir)
        if metadata.get("sync_status") != SyncStatus.IN_PROGRESS.value:
            metadata["sync_status"] = SyncStatus.IN_PROGRESS.value
            _flush_metadata(comment_storage, output_dir, metadata)
        validate_tasks_for_resume(sync_tasks, metadata, entity_label="subreddits")
        print(f"sync_records: resuming {output_dir}")
    else:
        sync_timestamp = get_current_timestamp()
        output_dir = comment_storage.create_new_run_dir(sync_timestamp)
        metadata = init_sync_metadata(config, config_path, sync_timestamp, sync_tasks)
        _flush_metadata(comment_storage, output_dir, metadata)
        print(f"sync_records: started new run {output_dir}")

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


def main(
    config: Path = typer.Option(
        DEFAULT_CONFIG,
        "--config",
        help="YAML config path or filename under configs/reddit/ (e.g. mirrorview.yaml)",
    ),
    resume: bool = typer.Option(
        False,
        "--resume",
        help="Resume the latest in-progress raw run for this dataset",
    ),
    run_dir: str | None = typer.Option(
        None,
        "--run-dir",
        help="Raw run timestamp directory name (requires --resume)",
    ),
) -> None:
    config_path = resolve_config_path(config, CONFIGS_DIR)
    sync_records(config_path, resume=resume, run_dir_name=run_dir)


if __name__ == "__main__":
    typer.run(main)
