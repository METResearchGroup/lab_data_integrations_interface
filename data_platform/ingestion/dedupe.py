from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from data_platform.utils.storage import StorageManager


def load_prior_seen_ids(
    storage: StorageManager,
    output_dir: Path,
    ingestion_params: dict[str, Any],
    id_column: str,
    *,
    filename: str | None = None,
    same_dataset_flag: str,
) -> set[str]:
    if ingestion_params.get("dedupe_across_datasets", True):
        return storage.load_seen_ids_from_platform_raw_runs(
            output_dir, id_column, filename=filename
        )
    if ingestion_params.get(same_dataset_flag):
        return storage.load_seen_ids_from_prior_runs(output_dir, id_column, filename=filename)
    return set()


def increment_metadata_counter(metadata: dict[str, Any], key: str, delta: int) -> None:
    metadata[key] = int(metadata.get(key, 0)) + delta


def append_deduped_rows(
    storage: StorageManager,
    output_dir: Path,
    rows: list[dict[str, Any]],
    id_column: str,
    *,
    prior_ids: set[str],
    filename: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Append rows not already seen. Returns (new_rows, skipped_count)."""
    seen_ids = prior_ids | storage.load_seen_ids(output_dir, id_column, filename=filename)
    new_rows = [row for row in rows if row[id_column] not in seen_ids]
    skipped = len(rows) - len(new_rows)
    if new_rows:
        storage.append_records(new_rows, output_dir, filename=filename)
    return new_rows, skipped


def persist_deduped_rows(
    storage: StorageManager,
    output_dir: Path,
    rows: list[dict[str, Any]],
    id_column: str,
    metadata: dict[str, Any],
    *,
    prior_ids: set[str],
    filename: str | None = None,
    skipped_key: str,
    row_count_key: str = "row_count",
) -> list[dict[str, Any]]:
    """Append deduped rows and update run-level skip and row-count metadata."""
    new_rows, skipped = append_deduped_rows(
        storage,
        output_dir,
        rows,
        id_column,
        prior_ids=prior_ids,
        filename=filename,
    )
    increment_metadata_counter(metadata, skipped_key, skipped)
    metadata[row_count_key] = len(storage.load_seen_ids(output_dir, id_column, filename=filename))
    return new_rows


@dataclass(frozen=True)
class SubredditPersistResult:
    comment_count: int
    post_count: int


def persist_deduped_subreddit_rows(
    comment_storage: StorageManager,
    post_storage: StorageManager,
    output_dir: Path,
    post_rows: list[dict[str, Any]],
    comment_rows: list[dict[str, Any]],
    metadata: dict[str, Any],
    *,
    include_comments: bool,
    include_posts: bool,
    prior_comment_ids: set[str],
    prior_post_ids: set[str],
    comments_csv: str,
    posts_csv: str,
) -> SubredditPersistResult:
    """Append deduped Reddit posts/comments and update run-level metadata."""
    if include_posts and post_rows:
        _, posts_skipped = append_deduped_rows(
            post_storage,
            output_dir,
            post_rows,
            "reddit_fullname",
            prior_ids=prior_post_ids,
            filename=posts_csv,
        )
        increment_metadata_counter(metadata, "posts_skipped_as_duplicates", posts_skipped)

    if include_comments and comment_rows:
        _, comments_skipped = append_deduped_rows(
            comment_storage,
            output_dir,
            comment_rows,
            "comment_fullname",
            prior_ids=prior_comment_ids,
            filename=comments_csv,
        )
        increment_metadata_counter(metadata, "comments_skipped_as_duplicates", comments_skipped)

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
    metadata["row_count"] = comment_count
    metadata["post_row_count"] = post_count
    return SubredditPersistResult(comment_count=comment_count, post_count=post_count)
