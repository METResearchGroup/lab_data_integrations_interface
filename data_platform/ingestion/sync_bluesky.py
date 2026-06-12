"""Sync Bluesky posts from YAML config to raw CSV storage.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/ingestion/sync_bluesky.py

    PYTHONPATH=. uv run python data_platform/ingestion/sync_bluesky.py --config mirrorview.yaml

Resume the latest in-progress run for a dataset:

    PYTHONPATH=. uv run python data_platform/ingestion/sync_bluesky.py \\
        --config mirrorview_scale.yaml --resume

Resume a specific raw run timestamp:

    PYTHONPATH=. uv run python data_platform/ingestion/sync_bluesky.py \\
        --config mirrorview_scale.yaml --resume --run-dir 2026_05_30-12:00:00

Ingestion YAML must include `dataset_id` (e.g. bluesky_<uuid>).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atproto import Client

from data_platform.ingestion.bluesky_retry import retry_bluesky_request
from data_platform.ingestion.dedupe import append_deduped_rows, load_prior_seen_ids
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
from data_platform.utils.storage import BlueskyStorageManager
from lib.load_env_vars import EnvVarsContainer

CONFIGS_DIR = Path(__file__).resolve().parent / "configs/bluesky"
DEFAULT_CONFIG = CONFIGS_DIR / "default.yaml"
REPO_ROOT = Path(__file__).resolve().parents[2]
API_MAX_LIMIT = 100

POSTS_RECORD_TYPE = "app.bsky.feed.post"
DEFAULT_QUERY_BATCH_SIZE = 5


@dataclass(frozen=True)
class BlueskyTask:
    task_id: str
    query: str
    source_keywords: list[str] | None = None


def _quote_query_term(keyword: str) -> str:
    if any(ch.isspace() for ch in keyword) or any(ch in keyword for ch in ('"', ":", "(", ")")):
        escaped = keyword.replace('"', '\\"')
        return f'"{escaped}"'
    return keyword


def build_or_query(keywords: list[str]) -> str:
    """Build a searchPosts q string using Bluesky's pipe-delimited OR syntax."""
    return " | ".join(_quote_query_term(keyword) for keyword in keywords)


def _query_batch_size(ingestion_params: dict[str, Any]) -> int:
    return int(ingestion_params.get("query_batch_size", DEFAULT_QUERY_BATCH_SIZE))


def _chunk_keywords(keywords: list[str], batch_size: int) -> list[list[str]]:
    return [keywords[i : i + batch_size] for i in range(0, len(keywords), batch_size)]


def build_sync_tasks(ingestion_params: dict[str, Any]) -> list[BlueskyTask]:
    """Return sync tasks keyed by task_id for checkpointing."""
    keyword = ingestion_params.get("keyword")
    batch_size = _query_batch_size(ingestion_params)
    if isinstance(keyword, list):
        items: list[BlueskyTask] = []
        for index, chunk in enumerate(_chunk_keywords(keyword, batch_size)):
            batch_id = f"posts_batch_{index + 1}"
            query = build_or_query(chunk)
            if batch_size == 1:
                task_id = chunk[0]
                source_keywords = None
            else:
                task_id = batch_id
                source_keywords = chunk
            items.append(
                BlueskyTask(
                    task_id=task_id,
                    query=query,
                    source_keywords=source_keywords,
                )
            )
        return items
    if isinstance(keyword, str) and keyword:
        return [BlueskyTask(task_id=keyword, query=keyword)]

    raise ValueError("ingestion_params must include 'keyword' as a string or list of strings")


def _posts_to_rows(response: Any) -> list[dict[str, Any]]:
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
    """Fetch up to ingestion_params.limit posts for a single query, paginating with cursor."""
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
    return {
        "status": TaskStatus.PENDING.value,
        "kind": "bluesky",
        "source_keywords": task.source_keywords,
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
    max_rows_int = parse_max_rows(ingestion_params)
    prior_uris = load_prior_seen_ids(
        storage,
        output_dir,
        ingestion_params,
        "uri",
        filename=csv_filename,
        same_dataset_flag="dedupe_posts_from_prior_raw_runs",
    )
    posts_skipped = int(metadata.get("posts_skipped_as_duplicates", 0))

    def process_task(task: BlueskyTask, entry: dict[str, Any]) -> None:
        nonlocal posts_skipped

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

        new_rows, skipped = append_deduped_rows(
            storage,
            output_dir,
            rows,
            "uri",
            prior_ids=prior_uris,
            filename=csv_filename,
        )
        posts_skipped += skipped
        metadata["posts_skipped_as_duplicates"] = posts_skipped
        metadata["row_count"] = len(storage.load_seen_ids(output_dir, "uri", filename=csv_filename))
        entry["status"] = TaskStatus.COMPLETED.value
        entry["pages_fetched"] = stats["pages_fetched"]
        entry["rows_collected"] = stats["rows_collected"]
        entry["hits_total"] = stats["hits_total"]
        entry["last_error"] = None
        flush_run_metadata(storage, output_dir, metadata)

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


load_config = load_yaml_config


def setup_client() -> Client:
    client = Client()
    client.login(
        EnvVarsContainer.get_env_var("BLUESKY_HANDLE", required=True),
        EnvVarsContainer.get_env_var("BLUESKY_PASSWORD", required=True),
    )
    return client


def sync_records(
    config_path: Path = DEFAULT_CONFIG,
    *,
    resume: bool = False,
    run_dir_name: str | None = None,
) -> Path:
    """Fetch Bluesky records per config and write raw CSV + metadata."""
    config = load_config(config_path)
    dataset_id = require_dataset_id(config, platform="bluesky")
    storage = BlueskyStorageManager("raw", dataset_id)

    ensure_dataset_manifest(
        storage,
        "bluesky",
        dataset_id,
        config,
        config_path,
        repo_root=REPO_ROOT,
    )

    ingestion_params = config["ingestion_params"]
    sync_tasks = build_sync_tasks(ingestion_params)
    record_types: list[str] = config["record_types"]

    if POSTS_RECORD_TYPE not in record_types:
        raise ValueError(f"Unsupported record types for checkpoint sync: {record_types}")

    csv_filename = record_type_to_filename(POSTS_RECORD_TYPE)
    client = setup_client()

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
    run_sync_cli(
        configs_dir=CONFIGS_DIR,
        default_config=DEFAULT_CONFIG,
        sync_records_fn=sync_records,
        config_help="YAML config path or filename under configs/bluesky/ (e.g. mirrorview.yaml)",
    )


if __name__ == "__main__":
    main()
