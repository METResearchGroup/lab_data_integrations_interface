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

from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    require_dataset_id,
    run_checkpointed_sync,
    run_sync_cli,
)
from data_platform.ingestion.sync_clients import init_twitter_client
from data_platform.ingestion.twitter_client import fetch_posts_for_keyword
from data_platform.utils.config_paths import load_yaml_config
from data_platform.utils.storage import TwitterStorageManager

CONFIGS_DIR = Path(__file__).resolve().parent / "configs/twitter"
DEFAULT_CONFIG = CONFIGS_DIR / "default.yaml"
REPO_ROOT = Path(__file__).resolve().parents[2]
POSTS_CSV = "posts.csv"


@dataclass(frozen=True)
class TwitterTask:
    task_id: str
    keyword: str


def build_sync_tasks(ingestion_params: dict[str, Any]) -> list[TwitterTask]:
    keyword = ingestion_params.get("keyword")
    if isinstance(keyword, list) and keyword:
        return [TwitterTask(task_id=str(k), keyword=str(k)) for k in keyword]
    if isinstance(keyword, str) and keyword:
        return [TwitterTask(task_id=keyword, keyword=keyword)]
    raise ValueError("ingestion_params must include 'keyword' as a string or list of strings")


def _initial_task_progress(task: TwitterTask) -> dict[str, Any]:
    return {
        "status": TaskStatus.PENDING.value,
        "kind": "twitter",
        "keyword": task.keyword,
        "pages_fetched": 0,
        "rows_collected": 0,
        "last_error": None,
    }


def init_sync_metadata(
    config: dict[str, Any],
    config_path: Path,
    sync_timestamp: str,
    sync_tasks: list[TwitterTask],
) -> dict[str, Any]:
    return build_base_sync_metadata(
        config,
        config_path,
        sync_timestamp,
        sync_tasks,
        task_progress_builder=_initial_task_progress,
    )


def _effective_limit_per_keyword(ingestion_params: dict[str, Any], remaining: int | None) -> int:
    per_keyword = int(ingestion_params.get("limit_per_keyword", 25))
    if remaining is None:
        return per_keyword
    return max(0, min(per_keyword, remaining))


def _remaining_row_budget(metadata: dict[str, Any], max_rows_int: int | None) -> int | None:
    if max_rows_int is None:
        return None
    return max_rows_int - metadata["row_count"]


def run_sync_tasks(
    client: Any,
    ingestion_params: dict[str, Any],
    output_dir: Path,
    storage: TwitterStorageManager,
    metadata: dict[str, Any],
    sync_tasks: list[TwitterTask],
    *,
    sync_timestamp: str,
    csv_filename: str,
) -> None:
    max_rows_int = parse_max_rows(ingestion_params)
    lang = str(ingestion_params.get("lang", "en"))
    exclude = list(ingestion_params.get("exclude", ["reply", "retweet", "quote"]))
    prior_tweet_ids = load_prior_seen_ids(
        storage,
        output_dir,
        ingestion_params,
        "tweet_id",
        filename=csv_filename,
        same_dataset_flag="dedupe_tweets_from_prior_raw_runs",
    )

    def process_task(task: TwitterTask, entry: dict[str, Any]) -> None:
        mark_task_in_progress(entry, storage, output_dir, metadata)

        limit = _effective_limit_per_keyword(
            ingestion_params,
            _remaining_row_budget(metadata, max_rows_int),
        )
        try:
            rows, stats = fetch_posts_for_keyword(
                client,
                task.keyword,
                limit=limit,
                lang=lang,
                exclude=exclude,
                sync_timestamp=sync_timestamp,
            )
        except Exception as exc:  # noqa: BLE001 — record and continue
            mark_task_failed(entry, exc, task.task_id, storage, output_dir, metadata)
            return

        new_rows = persist_deduped_rows(
            storage,
            output_dir,
            rows,
            "tweet_id",
            metadata,
            prior_ids=prior_tweet_ids,
            filename=csv_filename,
            skipped_key="tweets_skipped_as_duplicates",
        )
        mark_task_completed(
            entry,
            storage,
            output_dir,
            metadata,
            entry_updates={
                "pages_fetched": stats["pages_fetched"],
                "rows_collected": stats["rows_collected"],
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


load_config = load_yaml_config


def sync_records(
    config_path: Path = DEFAULT_CONFIG,
    *,
    resume: bool = False,
    run_dir_name: str | None = None,
) -> Path:
    """Fetch Twitter records per config and write raw CSV + metadata."""
    config = load_config(config_path)
    dataset_id = require_dataset_id(config, platform="twitter")
    storage = TwitterStorageManager("raw", dataset_id)

    ensure_dataset_manifest(
        storage,
        "twitter",
        dataset_id,
        config,
        config_path,
        repo_root=REPO_ROOT,
    )

    ingestion_params = config["ingestion_params"]
    sync_tasks = build_sync_tasks(ingestion_params)
    client = init_twitter_client()

    output_dir, metadata = prepare_sync_run(
        storage,
        sync_tasks,
        resume=resume,
        run_dir_name=run_dir_name,
        init_metadata_fn=lambda ts: init_sync_metadata(config, config_path, ts, sync_tasks),
        entity_label="keywords",
    )
    sync_timestamp = str(metadata["sync_timestamp"])

    run_sync_tasks(
        client,
        ingestion_params,
        output_dir,
        storage,
        metadata,
        sync_tasks,
        sync_timestamp=sync_timestamp,
        csv_filename=POSTS_CSV,
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
        config_help="YAML config path or filename under configs/twitter/ (e.g. mirrorview.yaml)",
    )


if __name__ == "__main__":
    main()
