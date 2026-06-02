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

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import typer
from atproto import Client
from tqdm import tqdm

from data_platform.ingestion.bluesky_retry import retry_bluesky_request
from data_platform.ingestion.sync_checkpoint import (
    flush_sync_metadata,
    init_sync_metadata_base,
    mark_remaining_skipped,
    sync_status_done,
)
from data_platform.ingestion.sync_runner import (
    PreparedSyncRun,
    SyncPlatformSpec,
    make_sync_main,
    require_dataset_id,
    run_sync_from_config,
)
from data_platform.utils.config_paths import load_yaml_config
from data_platform.utils.storage import BlueskyStorageManager
from lib.load_env_vars import EnvVarsContainer

CONFIGS_DIR = Path(__file__).resolve().parent / "configs/bluesky"
DEFAULT_CONFIG = CONFIGS_DIR / "default.yaml"
API_MAX_LIMIT = 100

POSTS_RECORD_TYPE = "app.bsky.feed.post"
POSTS_CSV = "posts.csv"
DEFAULT_QUERY_BATCH_SIZE = 5


@dataclass(frozen=True)
class FetchWorkItem:
    batch_label: str
    query: str
    work_item_key: str
    keywords_in_batch: list[str] | None = None


def _record_type_to_filename(record_type: str, output_stem: str = "posts") -> str:
    if record_type == POSTS_RECORD_TYPE:
        return f"{output_stem}.csv"
    return f"{record_type.rsplit('.', 1)[-1]}.csv"


def _quote_query_term(keyword: str) -> str:
    if any(ch.isspace() for ch in keyword) or any(ch in keyword for ch in ('"', ":", "(", ")")):
        escaped = keyword.replace('"', '\\"')
        return f'"{escaped}"'
    return keyword


def build_or_query(keywords: list[str]) -> str:
    """Build a searchPosts q string using Bluesky's pipe-delimited OR syntax."""
    return " | ".join(_quote_query_term(keyword) for keyword in keywords)


def _query_batch_size(fetch: dict[str, Any]) -> int:
    return int(fetch.get("query_batch_size", DEFAULT_QUERY_BATCH_SIZE))


def _chunk_keywords(keywords: list[str], batch_size: int) -> list[list[str]]:
    return [keywords[i : i + batch_size] for i in range(0, len(keywords), batch_size)]


def iter_fetch_work_items(fetch: dict[str, Any]) -> list[FetchWorkItem]:
    """Return work items as (batch_label, query, work_item_key) for checkpointing."""
    keyword = fetch.get("keyword")
    batch_size = _query_batch_size(fetch)
    if isinstance(keyword, list):
        items: list[FetchWorkItem] = []
        for index, chunk in enumerate(_chunk_keywords(keyword, batch_size)):
            batch_label = f"posts_batch_{index + 1}"
            query = build_or_query(chunk)
            if batch_size == 1:
                work_item_key = chunk[0]
                keywords_in_batch = None
            else:
                work_item_key = batch_label
                keywords_in_batch = chunk
            items.append(
                FetchWorkItem(
                    batch_label=batch_label,
                    query=query,
                    work_item_key=work_item_key,
                    keywords_in_batch=keywords_in_batch,
                )
            )
        return items
    if isinstance(keyword, str) and keyword:
        return [
            FetchWorkItem(
                batch_label="posts",
                query=keyword,
                work_item_key=keyword,
            )
        ]

    raise ValueError("fetch config must include 'keyword' as a string or list of strings")


def _iter_fetch_queries(fetch: dict[str, Any]) -> list[tuple[str, str]]:
    return [(item.batch_label, item.query) for item in iter_fetch_work_items(fetch)]


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
    fetch: dict[str, Any],
    query: str,
    *,
    page_limit: int,
    cursor: str | None = None,
) -> Any:
    base_params = {
        "q": query,
        "limit": page_limit,
        "sort": fetch.get("sort", "latest"),
    }
    if cursor:
        base_params["cursor"] = cursor
    handle = fetch.get("handle")
    if handle:
        return client.app.bsky.feed.search_posts(
            params={**base_params, "author": handle},  # type: ignore[arg-type]
        )
    return client.app.bsky.feed.search_posts(params=base_params)  # type: ignore[arg-type]


def fetch_posts_for_keyword(
    client: Client,
    fetch: dict[str, Any],
    query: str,
    *,
    batch_label: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch up to fetch.limit posts for a single query, paginating with cursor."""
    target = int(fetch["limit"])
    rows: list[dict[str, Any]] = []
    cursor: str | None = None
    pages_fetched = 0
    hits_total: int | None = None

    while len(rows) < target:
        page_limit = min(target - len(rows), API_MAX_LIMIT)
        response = _search_posts_page(client, fetch, query, page_limit=page_limit, cursor=cursor)
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
        "batch_label": batch_label,
        "query_len": len(query),
        "per_query_limit": target,
        "pages_fetched": pages_fetched,
        "rows_collected": len(rows),
        "hits_total": hits_total,
    }
    return rows, stats


def _keyword_entry(item: FetchWorkItem) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "status": "pending",
        "batch_label": item.batch_label,
        "pages_fetched": 0,
        "rows_collected": 0,
        "hits_total": None,
        "last_error": None,
    }
    if item.keywords_in_batch is not None:
        entry["keywords_in_batch"] = item.keywords_in_batch
    return entry


def init_sync_metadata(
    config: dict[str, Any],
    config_path: Path,
    sync_timestamp: str,
    work_items: list[FetchWorkItem],
) -> dict[str, Any]:
    dataset_id = require_dataset_id(config, hint="bluesky_<uuid>")
    return init_sync_metadata_base(
        config,
        config_path,
        sync_timestamp,
        dataset_id=dataset_id,
        metadata_bucket="keywords",
        entries={item.work_item_key: _keyword_entry(item) for item in work_items},
    )


def run_keyword_sync_loop(
    client: Client,
    fetch: dict[str, Any],
    output_dir: Path,
    storage: BlueskyStorageManager,
    metadata: dict[str, Any],
    work_items: list[FetchWorkItem],
    *,
    csv_filename: str,
) -> None:
    max_rows = fetch.get("max_rows")
    max_rows_int = int(max_rows) if max_rows is not None else None

    for item in tqdm(
        work_items,
        desc="Syncing keywords",
        disable=not sys.stderr.isatty(),
    ):
        entry = metadata["keywords"][item.work_item_key]
        status = entry["status"]
        if status in ("completed", "skipped"):
            continue

        if max_rows_int is not None and metadata["row_count"] >= max_rows_int:
            mark_remaining_skipped(metadata, metadata_bucket="keywords")
            flush_sync_metadata(storage, output_dir, metadata)
            break

        entry["status"] = "in_progress"
        entry["last_error"] = None
        flush_sync_metadata(storage, output_dir, metadata)

        try:
            rows, stats = fetch_posts_for_keyword(
                client,
                fetch,
                item.query,
                batch_label=item.batch_label,
            )
        except Exception as exc:  # noqa: BLE001 — record and continue
            entry["status"] = "failed"
            entry["last_error"] = str(exc)
            flush_sync_metadata(storage, output_dir, metadata)
            print(f"sync_records: {item.work_item_key} failed: {exc}")
            continue

        seen_uris = storage.load_seen_uris(output_dir, filename=csv_filename)
        new_rows = [row for row in rows if row["uri"] not in seen_uris]
        if new_rows:
            storage.append_records(new_rows, output_dir, filename=csv_filename)

        metadata["row_count"] = len(storage.load_seen_uris(output_dir, filename=csv_filename))
        entry["status"] = "completed"
        entry["pages_fetched"] = stats["pages_fetched"]
        entry["rows_collected"] = stats["rows_collected"]
        entry["hits_total"] = stats["hits_total"]
        entry["last_error"] = None
        flush_sync_metadata(storage, output_dir, metadata)

        print(
            f"sync_records: {item.work_item_key} -> {stats['rows_collected']} rows "
            f"(appended {len(new_rows)}, pages={stats['pages_fetched']})"
        )

        if max_rows_int is not None and metadata["row_count"] >= max_rows_int:
            mark_remaining_skipped(metadata, metadata_bucket="keywords")
            flush_sync_metadata(storage, output_dir, metadata)
            break

    metadata["sync_status"] = sync_status_done(metadata, metadata_bucket="keywords")
    flush_sync_metadata(storage, output_dir, metadata)


load_config = load_yaml_config


def setup_client() -> Client:
    client = Client()
    client.login(
        EnvVarsContainer.get_env_var("BLUESKY_HANDLE", required=True),
        EnvVarsContainer.get_env_var("BLUESKY_PASSWORD", required=True),
    )
    return client


def _run_bluesky_sync_loop(prepared: PreparedSyncRun) -> None:
    record_types: list[str] = prepared.config["record_types"]
    if POSTS_RECORD_TYPE not in record_types:
        raise ValueError(f"Unsupported record types for checkpoint sync: {record_types}")

    csv_filename = _record_type_to_filename(POSTS_RECORD_TYPE, "posts")
    client = setup_client()
    storage = cast(BlueskyStorageManager, prepared.storage)
    run_keyword_sync_loop(
        client,
        prepared.fetch,
        prepared.output_dir,
        storage,
        prepared.metadata,
        prepared.work_items,
        csv_filename=csv_filename,
    )


_BLUESKY_SYNC_SPEC = SyncPlatformSpec(
    platform="bluesky",
    dataset_id_hint="bluesky_<uuid>",
    metadata_bucket="keywords",
    entity_label="keywords",
    create_storage=lambda dataset_id: BlueskyStorageManager("raw", dataset_id),
    iter_work_items=iter_fetch_work_items,
    init_sync_metadata=init_sync_metadata,
    run_loop=_run_bluesky_sync_loop,
)


def sync_records(
    config_path: Path = DEFAULT_CONFIG,
    *,
    resume: bool = False,
    run_dir_name: str | None = None,
) -> Path:
    """Fetch Bluesky records per config and write raw CSV + metadata."""
    return run_sync_from_config(
        config_path,
        resume=resume,
        run_dir_name=run_dir_name,
        spec=_BLUESKY_SYNC_SPEC,
    )


main = make_sync_main(
    sync_records=sync_records,
    configs_dir=CONFIGS_DIR,
    default_config=DEFAULT_CONFIG,
    config_help_subdir="bluesky",
)


if __name__ == "__main__":
    typer.run(main)
