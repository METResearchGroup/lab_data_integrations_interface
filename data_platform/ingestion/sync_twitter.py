"""Sync Twitter posts from YAML config to raw CSV storage.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/ingestion/sync_twitter.py

    PYTHONPATH=. uv run python data_platform/ingestion/sync_twitter.py --config mirrorview.yaml

Resume the latest in-progress run for a dataset:

    PYTHONPATH=. uv run python data_platform/ingestion/sync_twitter.py \\
        --config mirrorview.yaml --resume

Resume a specific raw run timestamp:

    PYTHONPATH=. uv run python data_platform/ingestion/sync_twitter.py \\
        --config mirrorview.yaml --resume --run-dir 2026_06_01-12:00:00

Ingestion YAML must include `dataset_id` (e.g. twitter_<uuid>).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import typer
from tqdm import tqdm

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
from data_platform.ingestion.twitter_client import fetch_posts_for_keyword, init_twitter_client
from data_platform.utils.config_paths import load_yaml_config
from data_platform.utils.storage import TwitterStorageManager

CONFIGS_DIR = Path(__file__).resolve().parent / "configs/twitter"
DEFAULT_CONFIG = CONFIGS_DIR / "default.yaml"
POSTS_CSV = "posts.csv"


@dataclass(frozen=True)
class FetchWorkItem:
    work_item_key: str
    keyword: str


def iter_fetch_work_items(fetch: dict[str, Any]) -> list[FetchWorkItem]:
    keyword = fetch.get("keyword")
    if isinstance(keyword, list) and keyword:
        return [FetchWorkItem(work_item_key=str(k), keyword=str(k)) for k in keyword]
    if isinstance(keyword, str) and keyword:
        return [FetchWorkItem(work_item_key=keyword, keyword=keyword)]
    raise ValueError("fetch config must include 'keyword' as a string or list of strings")


def _keyword_entry(item: FetchWorkItem) -> dict[str, Any]:
    return {
        "status": "pending",
        "keyword": item.keyword,
        "pages_fetched": 0,
        "rows_collected": 0,
        "last_error": None,
    }


def init_sync_metadata(
    config: dict[str, Any],
    config_path: Path,
    sync_timestamp: str,
    work_items: list[FetchWorkItem],
) -> dict[str, Any]:
    dataset_id = require_dataset_id(config, hint="twitter_<uuid>")
    return init_sync_metadata_base(
        config,
        config_path,
        sync_timestamp,
        dataset_id=dataset_id,
        metadata_bucket="keywords",
        entries={item.work_item_key: _keyword_entry(item) for item in work_items},
    )


def _effective_limit_per_keyword(fetch: dict[str, Any], remaining: int | None) -> int:
    per_keyword = int(fetch.get("limit_per_keyword", 25))
    if remaining is None:
        return per_keyword
    return max(0, min(per_keyword, remaining))


def _stop_at_max_rows(
    storage: TwitterStorageManager,
    output_dir: Path,
    metadata: dict[str, Any],
    max_rows_int: int | None,
) -> bool:
    """Mark pending keywords skipped and flush when row cap is reached."""
    if max_rows_int is None or metadata["row_count"] < max_rows_int:
        return False
    mark_remaining_skipped(metadata, metadata_bucket="keywords")
    flush_sync_metadata(storage, output_dir, metadata)
    return True


def _remaining_row_budget(metadata: dict[str, Any], max_rows_int: int | None) -> int | None:
    if max_rows_int is None:
        return None
    return max_rows_int - metadata["row_count"]


def _sync_one_keyword(
    client: Any,
    *,
    item: FetchWorkItem,
    entry: dict[str, Any],
    fetch: dict[str, Any],
    output_dir: Path,
    storage: TwitterStorageManager,
    metadata: dict[str, Any],
    sync_timestamp: str,
    csv_filename: str,
    lang: str,
    exclude: list[str],
    remaining: int | None,
    prior_tweet_ids: set[str],
) -> None:
    entry["status"] = "in_progress"
    entry["last_error"] = None
    flush_sync_metadata(storage, output_dir, metadata)

    limit = _effective_limit_per_keyword(fetch, remaining)
    try:
        rows, stats = fetch_posts_for_keyword(
            client,
            item.keyword,
            limit=limit,
            lang=lang,
            exclude=exclude,
            sync_timestamp=sync_timestamp,
        )
    except Exception as exc:  # noqa: BLE001 — record and continue
        entry["status"] = "failed"
        entry["last_error"] = str(exc)
        flush_sync_metadata(storage, output_dir, metadata)
        print(f"sync_records: {item.work_item_key} failed: {exc}")
        return

    seen_ids = prior_tweet_ids | storage.load_seen_tweet_ids(output_dir, filename=csv_filename)
    new_rows = [row for row in rows if row["tweet_id"] not in seen_ids]
    tweets_skipped = len(rows) - len(new_rows)
    metadata["tweets_skipped_as_duplicates"] = (
        int(metadata.get("tweets_skipped_as_duplicates", 0)) + tweets_skipped
    )
    if new_rows:
        storage.append_records(new_rows, output_dir, filename=csv_filename)

    metadata["row_count"] = len(storage.load_seen_tweet_ids(output_dir, filename=csv_filename))
    entry["status"] = "completed"
    entry["pages_fetched"] = stats["pages_fetched"]
    entry["rows_collected"] = stats["rows_collected"]
    entry["last_error"] = None
    flush_sync_metadata(storage, output_dir, metadata)

    print(
        f"sync_records: {item.work_item_key} -> {stats['rows_collected']} rows "
        f"(appended {len(new_rows)}, pages={stats['pages_fetched']})"
    )


def run_keyword_sync_loop(
    client: Any,
    fetch: dict[str, Any],
    output_dir: Path,
    storage: TwitterStorageManager,
    metadata: dict[str, Any],
    work_items: list[FetchWorkItem],
    *,
    sync_timestamp: str,
    csv_filename: str,
) -> None:
    max_rows = fetch.get("max_rows")
    max_rows_int = int(max_rows) if max_rows is not None else None
    lang = str(fetch.get("lang", "en"))
    exclude = list(fetch.get("exclude", ["reply", "retweet", "quote"]))
    prior_tweet_ids: set[str] = set()
    if fetch.get("dedupe_tweets_from_prior_raw_runs"):
        prior_tweet_ids = storage.load_seen_ids_from_prior_runs(
            output_dir, "tweet_id", filename=csv_filename
        )

    for item in tqdm(
        work_items,
        desc="Syncing keywords",
        disable=not sys.stderr.isatty(),
    ):
        entry = metadata["keywords"][item.work_item_key]
        if entry["status"] in ("completed", "skipped"):
            continue

        if _stop_at_max_rows(storage, output_dir, metadata, max_rows_int):
            break

        _sync_one_keyword(
            client,
            item=item,
            entry=entry,
            fetch=fetch,
            output_dir=output_dir,
            storage=storage,
            metadata=metadata,
            sync_timestamp=sync_timestamp,
            csv_filename=csv_filename,
            lang=lang,
            exclude=exclude,
            remaining=_remaining_row_budget(metadata, max_rows_int),
            prior_tweet_ids=prior_tweet_ids,
        )

        if _stop_at_max_rows(storage, output_dir, metadata, max_rows_int):
            break

    metadata["sync_status"] = sync_status_done(metadata, metadata_bucket="keywords")
    flush_sync_metadata(storage, output_dir, metadata)


load_config = load_yaml_config


def _run_twitter_sync_loop(prepared: PreparedSyncRun) -> None:
    client = init_twitter_client()
    storage = cast(TwitterStorageManager, prepared.storage)
    run_keyword_sync_loop(
        client,
        prepared.fetch,
        prepared.output_dir,
        storage,
        prepared.metadata,
        prepared.work_items,
        sync_timestamp=prepared.sync_timestamp,
        csv_filename=POSTS_CSV,
    )


_TWITTER_SYNC_SPEC = SyncPlatformSpec(
    platform="twitter",
    dataset_id_hint="twitter_<uuid>",
    metadata_bucket="keywords",
    entity_label="keywords",
    create_storage=lambda dataset_id: TwitterStorageManager("raw", dataset_id),
    iter_work_items=iter_fetch_work_items,
    init_sync_metadata=init_sync_metadata,
    run_loop=_run_twitter_sync_loop,
)


def sync_records(
    config_path: Path = DEFAULT_CONFIG,
    *,
    resume: bool = False,
    run_dir_name: str | None = None,
) -> Path:
    """Fetch Twitter records per config and write raw CSV + metadata."""
    return run_sync_from_config(
        config_path,
        resume=resume,
        run_dir_name=run_dir_name,
        spec=_TWITTER_SYNC_SPEC,
    )


main = make_sync_main(
    sync_records=sync_records,
    configs_dir=CONFIGS_DIR,
    default_config=DEFAULT_CONFIG,
    config_help_subdir="twitter",
)


if __name__ == "__main__":
    typer.run(main)
