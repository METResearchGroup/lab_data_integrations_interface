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
from typing import Any

import typer
from tqdm import tqdm

from data_platform.ingestion.dedupe import load_prior_seen_ids
from data_platform.ingestion.sync_checkpoint import (
    SyncStatus,
    TaskStatus,
    get_task_progress,
    mark_remaining_tasks_skipped,
    sync_status_from_tasks,
    validate_tasks_for_resume,
)
from data_platform.ingestion.twitter_client import fetch_posts_for_keyword, init_twitter_client
from data_platform.utils.config_paths import load_yaml_config, resolve_config_path
from data_platform.utils.dataset import validate_dataset_id, write_dataset_manifest
from data_platform.utils.storage import TwitterStorageManager
from lib.timestamp_utils import get_current_timestamp

CONFIGS_DIR = Path(__file__).resolve().parent / "configs/twitter"
DEFAULT_CONFIG = CONFIGS_DIR / "default.yaml"
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
        "tasks": {task.task_id: _initial_task_progress(task) for task in sync_tasks},
    }


def _flush_metadata(
    storage: TwitterStorageManager, run_dir: Path, metadata: dict[str, Any]
) -> None:
    storage.write_run_metadata_atomic(run_dir, metadata)


def _effective_limit_per_keyword(ingestion_params: dict[str, Any], remaining: int | None) -> int:
    per_keyword = int(ingestion_params.get("limit_per_keyword", 25))
    if remaining is None:
        return per_keyword
    return max(0, min(per_keyword, remaining))


def _stop_at_max_rows(
    storage: TwitterStorageManager,
    output_dir: Path,
    metadata: dict[str, Any],
    max_rows_int: int | None,
) -> bool:
    """Mark pending tasks skipped and flush when row cap is reached."""
    if max_rows_int is None or metadata["row_count"] < max_rows_int:
        return False
    mark_remaining_tasks_skipped(get_task_progress(metadata))
    _flush_metadata(storage, output_dir, metadata)
    return True


def _remaining_row_budget(metadata: dict[str, Any], max_rows_int: int | None) -> int | None:
    if max_rows_int is None:
        return None
    return max_rows_int - metadata["row_count"]


def _sync_one_task(
    client: Any,
    *,
    task: TwitterTask,
    entry: dict[str, Any],
    ingestion_params: dict[str, Any],
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
    entry["status"] = TaskStatus.IN_PROGRESS.value
    entry["last_error"] = None
    _flush_metadata(storage, output_dir, metadata)

    limit = _effective_limit_per_keyword(ingestion_params, remaining)
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
        entry["status"] = TaskStatus.FAILED.value
        entry["last_error"] = str(exc)
        _flush_metadata(storage, output_dir, metadata)
        print(f"sync_records: {task.task_id} failed: {exc}")
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
    entry["status"] = TaskStatus.COMPLETED.value
    entry["pages_fetched"] = stats["pages_fetched"]
    entry["rows_collected"] = stats["rows_collected"]
    entry["last_error"] = None
    _flush_metadata(storage, output_dir, metadata)

    print(
        f"sync_records: {task.task_id} -> {stats['rows_collected']} rows "
        f"(appended {len(new_rows)}, pages={stats['pages_fetched']})"
    )


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
    max_rows = ingestion_params.get("max_rows")
    max_rows_int = int(max_rows) if max_rows is not None else None
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
    progress = get_task_progress(metadata)

    for task in tqdm(
        sync_tasks,
        desc="Syncing keywords",
        disable=not sys.stderr.isatty(),
    ):
        entry = progress[task.task_id]
        if entry["status"] in (TaskStatus.COMPLETED.value, TaskStatus.SKIPPED.value):
            continue

        if _stop_at_max_rows(storage, output_dir, metadata, max_rows_int):
            break

        _sync_one_task(
            client,
            task=task,
            entry=entry,
            ingestion_params=ingestion_params,
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

    metadata["sync_status"] = sync_status_from_tasks(progress).value
    _flush_metadata(storage, output_dir, metadata)


def find_resume_run_dir(
    storage: TwitterStorageManager,
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
        raise ValueError("ingestion config must include dataset_id (twitter_<uuid>)")
    return validate_dataset_id(str(raw))


def sync_records(
    config_path: Path = DEFAULT_CONFIG,
    *,
    resume: bool = False,
    run_dir_name: str | None = None,
) -> Path:
    """Fetch Twitter records per config and write raw CSV + metadata."""
    if run_dir_name is not None and not resume:
        raise ValueError("--run-dir requires --resume")

    config = load_config(config_path)
    dataset_id = _require_dataset_id(config)
    storage = TwitterStorageManager("raw", dataset_id)

    manifest_path = storage.root_dir.parent / "dataset.json"
    if not manifest_path.exists():
        write_dataset_manifest(
            "twitter",
            dataset_id,
            name=str(config["name"]),
            ingestion_config=str(config_path.relative_to(Path(__file__).resolve().parents[2])),
        )

    ingestion_params = config["ingestion_params"]
    sync_tasks = build_sync_tasks(ingestion_params)
    client = init_twitter_client()

    if resume:
        output_dir = find_resume_run_dir(storage, run_dir_name=run_dir_name)
        metadata = storage.load_run_metadata(output_dir)
        if metadata.get("sync_status") != SyncStatus.IN_PROGRESS.value:
            metadata["sync_status"] = SyncStatus.IN_PROGRESS.value
            _flush_metadata(storage, output_dir, metadata)
        validate_tasks_for_resume(sync_tasks, metadata, entity_label="keywords")
        sync_timestamp = str(metadata["sync_timestamp"])
        print(f"sync_records: resuming {output_dir}")
    else:
        sync_timestamp = get_current_timestamp()
        output_dir = storage.create_new_run_dir(sync_timestamp)
        metadata = init_sync_metadata(config, config_path, sync_timestamp, sync_tasks)
        _flush_metadata(storage, output_dir, metadata)
        print(f"sync_records: started new run {output_dir}")

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


def main(
    config: Path = typer.Option(
        DEFAULT_CONFIG,
        "--config",
        help="YAML config path or filename under configs/twitter/ (e.g. mirrorview.yaml)",
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
