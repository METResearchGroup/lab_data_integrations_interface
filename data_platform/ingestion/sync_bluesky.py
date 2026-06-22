"""Sync Bluesky posts from YAML config to raw CSV storage.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/ingestion/sync_bluesky.py \\
        --config data_platform/ingestion/configs/bluesky/mirrorview.yaml

Automatically resumes the most recent in-progress run for the dataset, or starts a new one.
Pin a specific run to resume with --run-dir:

    PYTHONPATH=. uv run python data_platform/ingestion/sync_bluesky.py \\
        --config data_platform/ingestion/configs/bluesky/mirrorview_scale.yaml \\
        --run-dir 2026_05_30-12:00:00

Ingestion YAML must include `dataset_id` (e.g. bluesky_<uuid>).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from data_platform.aws.constants import S3_BUCKET
from data_platform.aws.s3 import S3
from data_platform.ingestion.bluesky_retry import retry_bluesky_request
from data_platform.ingestion.sync_checkpoint import (
    SyncStatus,
    TaskStatus,
    build_base_sync_metadata,
    ensure_dataset_manifest,
    flush_run_metadata,
    get_task_progress,
    mark_task_completed,
    mark_task_failed,
    mark_task_in_progress,
    parse_max_rows,
    prepare_sync_run,
    require_dataset_id,
    run_checkpointed_sync,
    run_sync_cli,
    sync_status_from_tasks,
)
from data_platform.ingestion.sync_clients import init_bluesky_client
from data_platform.utils.config_paths import load_yaml_config
from data_platform.utils.deduplication import DedupeConfig, DedupeSession
from data_platform.utils.storage import BlueskyStorageManager, StorageStage

if TYPE_CHECKING:
    from atproto import Client

API_MAX_LIMIT = 100

POSTS_RECORD_TYPE = "app.bsky.feed.post"


@dataclass(frozen=True)
class BlueskyTask:
    """One checkpointed search unit: a stable task ID and the API query string."""

    task_id: str
    query: str


def _quote_query_term(keyword: str) -> str:
    """Wrap a keyword in quotes when it contains whitespace or search-syntax characters."""
    if any(ch.isspace() for ch in keyword) or any(ch in keyword for ch in ('"', ":", "(", ")")):
        escaped = keyword.replace('"', '\\"')
        return f'"{escaped}"'
    return keyword


def build_sync_tasks(ingestion_params: dict[str, Any]) -> list[BlueskyTask]:
    """Build one checkpoint task per entry in ingestion_params.keywords."""
    keywords = ingestion_params.get("keywords")
    if not isinstance(keywords, list) or not keywords:
        raise ValueError("ingestion_params must include 'keywords' as a non-empty list of strings")

    items: list[BlueskyTask] = []
    for raw in keywords:
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("ingestion_params.keywords entries must be non-empty strings")
        keyword = raw.strip()
        items.append(BlueskyTask(task_id=keyword, query=_quote_query_term(keyword)))
    return items


def _posts_to_rows(response: Any) -> list[dict[str, Any]]:
    """Map a searchPosts API response to flat dict rows for CSV storage."""
    rows: list[dict[str, Any]] = []
    for post in response.posts:
        rkey = post.uri.split("/")[-1]
        rows.append(
            {
                "uri": post.uri,
                "url": f"https://bsky.app/profile/{post.author.handle}/post/{rkey}",
                "author_handle": post.author.handle,
                "text": post.record.text,  # type: ignore[union-attr]
                "created_at": post.record.created_at,  # type: ignore[union-attr]
                "like_count": post.like_count,
                "repost_count": post.repost_count,
                "reply_count": post.reply_count,
                "quote_count": post.quote_count,
            }
        )
    return rows


@retry_bluesky_request()
def _search_posts_page(
    client: Client,
    ingestion_params: dict[str, Any],
    query: str,
    *,
    page_limit: int,
    cursor: str | None = None,
) -> Any:
    """Fetch one page of searchPosts results, optionally scoped to a single author handle."""
    base_params = {
        "q": query,
        "limit": page_limit,
        "sort": ingestion_params.get("sort", "latest"),
    }
    if cursor:
        base_params["cursor"] = cursor
    handle = ingestion_params.get("handle")
    if handle:
        return client.app.bsky.feed.search_posts(
            params={**base_params, "author": handle},  # type: ignore[arg-type]
        )
    return client.app.bsky.feed.search_posts(params=base_params)  # type: ignore[arg-type]


def fetch_posts_for_keyword(
    client: Client,
    ingestion_params: dict[str, Any],
    query: str,
    *,
    task_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Paginate searchPosts until limit rows are collected or results are exhausted.

    Returns rows and per-task stats (pages fetched, hits_total from the first page, etc.).
    """
    target = int(ingestion_params["limit"])
    rows: list[dict[str, Any]] = []
    cursor: str | None = None
    pages_fetched = 0
    hits_total: int | None = None

    while len(rows) < target:
        page_limit = min(target - len(rows), API_MAX_LIMIT)
        response = _search_posts_page(
            client, ingestion_params, query, page_limit=page_limit, cursor=cursor
        )
        if pages_fetched == 0:
            hits_total = response.hits_total
        page_rows = _posts_to_rows(response)
        if not page_rows:
            break
        rows.extend(page_rows)
        pages_fetched += 1
        cursor = response.cursor
        if not cursor:
            break

    rows = rows[:target]
    stats = {
        "task_id": task_id,
        "query_len": len(query),
        "per_query_limit": target,
        "pages_fetched": pages_fetched,
        "rows_collected": len(rows),
        "hits_total": hits_total,
    }
    return rows, stats


def _initial_task_progress(task: BlueskyTask) -> dict[str, Any]:
    """Return the pending task-ledger entry written into run metadata at sync start."""
    return {
        "status": TaskStatus.PENDING.value,
        "kind": "bluesky",
        "keyword": task.task_id,
        "pages_fetched": 0,
        "rows_collected": 0,
        "hits_total": None,
        "last_error": None,
    }


def init_sync_metadata(
    config: dict[str, Any],
    config_path: Path,
    sync_timestamp: str,
    sync_tasks: list[BlueskyTask],
) -> dict[str, Any]:
    """Build the initial metadata.json payload for a new raw run directory."""
    return build_base_sync_metadata(
        config,
        config_path,
        sync_timestamp,
        sync_tasks,
        task_progress_builder=_initial_task_progress,
    )


def run_sync_tasks(
    client: Client,
    ingestion_params: dict[str, Any],
    output_dir: Path,
    storage: BlueskyStorageManager,
    metadata: dict[str, Any],
    sync_tasks: list[BlueskyTask],
    *,
    filename: str,
) -> None:
    """Run the checkpointed keyword loop: fetch, dedupe-append, and flush metadata per task.

    Skips completed tasks on resume, stops early when max_rows is reached, and records failures
    without aborting the full run.
    """
    max_rows_int = parse_max_rows(ingestion_params)
    dedupe_session = DedupeSession(DedupeConfig(id_column="uri", filename=filename))
    dedupe_session.warm(storage, output_dir)

    def process_task(task: BlueskyTask, entry: dict[str, Any]) -> None:
        """Fetch one keyword, persist deduped rows, and update the task ledger entry."""
        mark_task_in_progress(entry, storage, output_dir, metadata)

        try:
            rows, stats = fetch_posts_for_keyword(
                client,
                ingestion_params,
                task.query,
                task_id=task.task_id,
            )
        except Exception as exc:  # noqa: BLE001 — record and continue
            mark_task_failed(entry, exc, task.task_id, storage, output_dir, metadata)
            return

        result = storage.append_deduped_records(
            rows,
            output_dir,
            dedupe_session=dedupe_session,
            filename=filename,
        )
        metadata["posts_skipped_as_duplicates"] = (
            int(metadata.get("posts_skipped_as_duplicates", 0)) + result.skipped
        )
        metadata["row_count"] = len(dedupe_session.seen_ids)
        mark_task_completed(
            entry,
            storage,
            output_dir,
            metadata,
            entry_updates={
                "pages_fetched": stats["pages_fetched"],
                "rows_collected": stats["rows_collected"],
                "hits_total": stats["hits_total"],
            },
        )

        print(
            f"sync_records: {task.task_id} -> {stats['rows_collected']} rows "
            f"(appended {result.kept}, pages={stats['pages_fetched']})"
        )

    run_checkpointed_sync(
        sync_tasks,
        metadata,
        storage,
        output_dir,
        max_rows_int=max_rows_int,
        tqdm_desc="Syncing keywords",
        process_task=process_task,
    )


def sync_records(
    config_path: Path,
    *,
    run_dir_name: str | None = None,
) -> Path:
    """Load config, prepare or resume a raw run, and sync all keyword tasks to posts.csv.

    Creates the dataset manifest on first run and returns the output run directory path.
    """
    config = load_yaml_config(config_path)
    dataset_id = require_dataset_id(config, platform="bluesky")
    storage = BlueskyStorageManager(StorageStage.RAW, dataset_id)

    ensure_dataset_manifest(
        storage,
        "bluesky",
        dataset_id,
        config,
        config_path,
    )

    ingestion_params = config["ingestion_params"]
    sync_tasks = build_sync_tasks(ingestion_params)
    record_types: list[str] = config["record_types"]

    if POSTS_RECORD_TYPE not in record_types:
        raise ValueError(f"Unsupported record types for checkpoint sync: {record_types}")

    filename = storage.records_filename
    client = init_bluesky_client()

    output_dir, metadata = prepare_sync_run(
        storage,
        sync_tasks,
        run_dir_name=run_dir_name,
        init_metadata_fn=lambda ts: init_sync_metadata(config, config_path, ts, sync_tasks),
        entity_label="keywords",
    )

    run_sync_tasks(
        client,
        ingestion_params,
        output_dir,
        storage,
        metadata,
        sync_tasks,
        filename=filename,
    )

    metadata["sync_status"] = sync_status_from_tasks(get_task_progress(metadata)).value
    if metadata["sync_status"] == SyncStatus.COMPLETED.value:
        key = f"raw/platform=bluesky/dataset_id={dataset_id}/run_dir={output_dir.name}/{filename}"
        S3().upload_file(output_dir / filename, S3_BUCKET, key)
        print(f"sync_records: uploaded raw to s3://{S3_BUCKET}/{key}")
        metadata["s3_upload_status"] = True
    flush_run_metadata(storage, output_dir, metadata)

    total_rows = metadata["row_count"]
    print(
        f"sync_records: wrote {total_rows} rows to {output_dir} (status={metadata['sync_status']})"
    )
    return output_dir


def main() -> None:
    """CLI entrypoint for sync_bluesky.py (--config, --resume, --run-dir)."""
    run_sync_cli(
        sync_records_fn=sync_records,
        config_help=(
            "Ingestion YAML path relative to the repo root "
            "(e.g. data_platform/ingestion/configs/bluesky/mirrorview.yaml)"
        ),
    )


if __name__ == "__main__":
    main()
