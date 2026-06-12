"""Sync Bluesky posts from YAML config to raw CSV storage.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/ingestion/sync_bluesky.py \\
        --config data_platform/ingestion/configs/bluesky/default.yaml

    PYTHONPATH=. uv run python data_platform/ingestion/sync_bluesky.py \\
        --config data_platform/ingestion/configs/bluesky/mirrorview.yaml

Resume the latest in-progress run for a dataset:

    PYTHONPATH=. uv run python data_platform/ingestion/sync_bluesky.py \\
        --config data_platform/ingestion/configs/bluesky/mirrorview_scale.yaml --resume

Resume a specific raw run timestamp:

    PYTHONPATH=. uv run python data_platform/ingestion/sync_bluesky.py \\
        --config data_platform/ingestion/configs/bluesky/mirrorview_scale.yaml --resume \\
        --run-dir 2026_05_30-12:00:00

Ingestion YAML must include `dataset_id` (e.g. bluesky_<uuid>).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from data_platform.ingestion.bluesky_retry import retry_bluesky_request
from data_platform.ingestion.dedupe import load_prior_seen_ids, persist_deduped_rows
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
from data_platform.ingestion.sync_clients import init_bluesky_client
from data_platform.utils.config_paths import load_yaml_config
from data_platform.utils.storage import BlueskyStorageManager

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
    """Paginate searchPosts until ingestion_params.limit rows are collected or results are exhausted.

    Returns the row list and per-task stats (pages fetched, hits_total from the first page, etc.).
    """
    target = int(ingestion_params["limit"])
    rows: list[dict[str, Any]] = []
    cursor: str | None = None
    pages_fetched = 0
    hits_total: int | None = None

    while len(rows) < target:
        page_limit = min(target - len(rows), API_MAX_LIMIT)
        response = _search_posts_page(client, ingestion_params, query, page_limit=page_limit, cursor=cursor)
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
    csv_filename: str,
) -> None:
    """Run the checkpointed keyword loop: fetch, dedupe-append, and flush metadata per task.

    Skips completed tasks on resume, stops early when max_rows is reached, and records failures
    without aborting the full run.
    """
    max_rows_int = parse_max_rows(ingestion_params)
    prior_uris = load_prior_seen_ids(
        storage,
        output_dir,
        ingestion_params,
        "uri",
        filename=csv_filename,
        same_dataset_flag="dedupe_posts_from_prior_raw_runs",
    )

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

        new_rows = persist_deduped_rows(
            storage,
            output_dir,
            rows,
            "uri",
            metadata,
            prior_ids=prior_uris,
            filename=csv_filename,
            skipped_key="posts_skipped_as_duplicates",
        )
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
            f"(appended {len(new_rows)}, pages={stats['pages_fetched']})"
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
    resume: bool = False,
    run_dir_name: str | None = None,
) -> Path:
    """Load config, prepare or resume a raw run, and sync all keyword tasks to posts.csv.

    Creates the dataset manifest on first run and returns the output run directory path.
    """
    config = load_yaml_config(config_path)
    dataset_id = require_dataset_id(config, platform="bluesky")
    storage = BlueskyStorageManager("raw", dataset_id)

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

    csv_filename = record_type_to_filename(POSTS_RECORD_TYPE)
    client = init_bluesky_client()

    output_dir, metadata = prepare_sync_run(
        storage,
        sync_tasks,
        resume=resume,
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
        csv_filename=csv_filename,
    )

    total_rows = metadata["row_count"]
    print(
        f"sync_records: wrote {total_rows} rows to {output_dir} (status={metadata['sync_status']})"
    )
    return output_dir


def main() -> None:
    """CLI entrypoint for sync_bluesky.py (--config, --resume, --run-dir)."""
    run_sync_cli(
        default_config=Path("data_platform/ingestion/configs/bluesky/default.yaml"),
        sync_records_fn=sync_records,
        config_help=(
            "Ingestion YAML path relative to the repo root "
            "(e.g. data_platform/ingestion/configs/bluesky/mirrorview.yaml)"
        ),
    )


if __name__ == "__main__":
    main()
