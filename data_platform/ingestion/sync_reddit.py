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

SubredditStatus = Literal["pending", "in_progress", "completed", "failed", "skipped"]
SyncStatus = Literal["in_progress", "completed"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FetchWorkItem:
    subreddit: str
    ledger_key: str


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
        ledger_key = _normalize_subreddit_key(subreddit)
        items.append(FetchWorkItem(subreddit=subreddit.strip(), ledger_key=ledger_key))
    return items


def _get_subreddit_listing(
    subreddit_obj: praw.models.Subreddit,
    listing: str,
    limit: int,
) -> list[praw.models.Submission]:
    if listing == "new":
        return list(subreddit_obj.new(limit=limit))
    if listing == "top":
        return list(subreddit_obj.top(limit=limit))
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
) -> list[praw.models.Submission]:
    return _get_subreddit_listing(reddit.subreddit(subreddit), listing, limit)


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
    comments_per_post = int(fetch.get("comments_per_post", 100))
    min_comment_body_length = int(fetch.get("min_comment_body_length", 30))

    try:
        submissions = _fetch_subreddit_page(reddit, subreddit, listing, limit)
    except prawcore.exceptions.NotFound:
        logger.warning("Subreddit not found: %s", subreddit)
        return [], [], {
            "subreddit": subreddit,
            "listing": listing,
            "limit_per_subreddit": limit,
            "posts_collected": 0,
            "comments_collected": 0,
        }

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
    dataset_id = _require_dataset_id(config)
    return {
        "sync_status": "in_progress",
        "dataset_id": dataset_id,
        "name": config["name"],
        "description": config["description"],
        "date": config["date"],
        "sync_timestamp": sync_timestamp,
        "ingestion_config": config_path.name,
        "record_types": config["record_types"],
        "fetch": config["fetch"],
        "row_count": 0,
        "post_row_count": 0,
        "subreddits": {item.ledger_key: _subreddit_entry(item) for item in work_items},
    }


def _flush_metadata(
    storage: RedditStorageManager, run_dir: Path, metadata: dict[str, Any]
) -> None:
    storage.write_run_metadata_atomic(run_dir, metadata)


def _mark_remaining_skipped(metadata: dict[str, Any]) -> None:
    for entry in metadata["subreddits"].values():
        if entry["status"] == "pending":
            entry["status"] = "skipped"


def _sync_status_done(metadata: dict[str, Any]) -> SyncStatus:
    statuses = {entry["status"] for entry in metadata["subreddits"].values()}
    unfinished = statuses - {"completed", "skipped"}
    return "completed" if not unfinished else "in_progress"


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

    for item in tqdm(
        work_items,
        desc="Syncing subreddits",
        disable=not sys.stderr.isatty(),
    ):
        entry = metadata["subreddits"][item.ledger_key]
        status = entry["status"]
        if status in ("completed", "skipped"):
            continue

        if max_rows_int is not None and metadata["row_count"] >= max_rows_int:
            _mark_remaining_skipped(metadata)
            _flush_metadata(comment_storage, output_dir, metadata)
            break

        entry["status"] = "in_progress"
        entry["last_error"] = None
        _flush_metadata(comment_storage, output_dir, metadata)

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
            _flush_metadata(comment_storage, output_dir, metadata)
            print(f"sync_records: {item.ledger_key} failed: {exc}")
            continue

        if include_posts and post_rows:
            seen_posts = post_storage.load_seen_ids(
                output_dir, "reddit_fullname", filename=POSTS_CSV
            )
            new_posts = [row for row in post_rows if row["reddit_fullname"] not in seen_posts]
            if new_posts:
                post_storage.append_records(new_posts, output_dir, filename=POSTS_CSV)

        if include_comments and comment_rows:
            seen_comments = comment_storage.load_seen_ids(
                output_dir, "comment_fullname", filename=COMMENTS_CSV
            )
            new_comments = [
                row for row in comment_rows if row["comment_fullname"] not in seen_comments
            ]
            if new_comments:
                comment_storage.append_records(new_comments, output_dir, filename=COMMENTS_CSV)

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
        _flush_metadata(comment_storage, output_dir, metadata)

        print(
            f"sync_records: {item.ledger_key} -> "
            f"{stats['comments_collected']} comments, {stats['posts_collected']} posts "
            f"(total comments={comment_count}, total posts={post_count})"
        )

        if max_rows_int is not None and metadata["row_count"] >= max_rows_int:
            _mark_remaining_skipped(metadata)
            _flush_metadata(comment_storage, output_dir, metadata)
            break

    metadata["sync_status"] = _sync_status_done(metadata)
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
        if metadata.get("sync_status") == "in_progress":
            candidates.append((path.name, path))

    if not candidates:
        raise FileNotFoundError(
            f"No in-progress raw run found under {storage.root_dir}. "
            "Start a new sync or pass --run-dir."
        )
    return max(candidates, key=lambda item: item[0])[1]


def merge_work_items_with_metadata(
    work_items: list[FetchWorkItem],
    metadata: dict[str, Any],
) -> list[FetchWorkItem]:
    ledger_keys = {item.ledger_key for item in work_items}
    metadata_keys = set(metadata.get("subreddits", {}))
    missing = ledger_keys - metadata_keys
    extra = metadata_keys - ledger_keys
    if missing or extra:
        raise ValueError(
            "Config subreddits do not match resume metadata "
            f"(missing in metadata: {sorted(missing)}, extra in metadata: {sorted(extra)})"
        )
    return work_items


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

    fetch = config["fetch"]
    work_items = iter_fetch_work_items(fetch)
    record_types: list[str] = config["record_types"]
    include_comments = COMMENTS_RECORD_TYPE in record_types
    include_posts = POSTS_RECORD_TYPE in record_types

    if not include_comments and not include_posts:
        raise ValueError(f"Unsupported record types for checkpoint sync: {record_types}")

    reddit = init_reddit()

    if resume:
        output_dir = find_resume_run_dir(comment_storage, run_dir_name=run_dir_name)
        metadata = comment_storage.load_run_metadata(output_dir)
        if metadata.get("sync_status") != "in_progress":
            metadata["sync_status"] = "in_progress"
            _flush_metadata(comment_storage, output_dir, metadata)
        work_items = merge_work_items_with_metadata(work_items, metadata)
        print(f"sync_records: resuming {output_dir}")
    else:
        sync_timestamp = get_current_timestamp()
        output_dir = comment_storage.create_new_run_dir(sync_timestamp)
        metadata = init_sync_metadata(config, config_path, sync_timestamp, work_items)
        _flush_metadata(comment_storage, output_dir, metadata)
        print(f"sync_records: started new run {output_dir}")

    run_subreddit_sync_loop(
        reddit,
        fetch,
        output_dir,
        comment_storage,
        post_storage,
        metadata,
        work_items,
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
