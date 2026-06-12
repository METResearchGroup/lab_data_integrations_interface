"""Shared checkpoint helpers for ingestion sync scripts."""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, TypeVar

import typer
from tqdm import tqdm

from data_platform.utils.config_paths import resolve_config_path
from data_platform.utils.dataset import validate_dataset_id, write_dataset_manifest
from data_platform.utils.storage import StorageManager
from lib.timestamp_utils import get_current_timestamp

RECORD_TYPE_FILENAMES: dict[str, str] = {
    "app.bsky.feed.post": "posts.csv",
    "reddit.comment": "comments.csv",
    "reddit.post": "posts.csv",
}


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class SyncStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


TASKS_KEY = "tasks"


class HasTaskId(Protocol):
    @property
    def task_id(self) -> str: ...


TTask = TypeVar("TTask", bound=HasTaskId)


def get_task_progress(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return metadata[TASKS_KEY]


def validate_tasks_for_resume(
    tasks: Sequence[HasTaskId],
    metadata: dict[str, Any],
    *,
    entity_label: str,
) -> None:
    progress = get_task_progress(metadata)
    task_ids = {task.task_id for task in tasks}
    metadata_ids = set(progress)
    missing = task_ids - metadata_ids
    extra = metadata_ids - task_ids
    if missing or extra:
        raise ValueError(
            f"Config {entity_label} do not match resume metadata "
            f"(missing in metadata: {sorted(missing)}, extra in metadata: {sorted(extra)})"
        )


def mark_remaining_tasks_skipped(progress: dict[str, dict[str, Any]]) -> None:
    for entry in progress.values():
        if entry["status"] == TaskStatus.PENDING.value:
            entry["status"] = TaskStatus.SKIPPED.value


def sync_status_from_tasks(progress: dict[str, dict[str, Any]]) -> SyncStatus:
    statuses = {entry["status"] for entry in progress.values()}
    unfinished = statuses - {TaskStatus.COMPLETED.value, TaskStatus.SKIPPED.value}
    return SyncStatus.COMPLETED if not unfinished else SyncStatus.IN_PROGRESS


def require_dataset_id(config: dict[str, Any], *, platform: str | None = None) -> str:
    raw = config.get("dataset_id")
    if not raw:
        hint = f" ({platform}_<uuid>)" if platform else ""
        raise ValueError(f"ingestion config must include dataset_id{hint}")
    return validate_dataset_id(str(raw))


def record_type_to_filename(record_type: str) -> str:
    if record_type in RECORD_TYPE_FILENAMES:
        return RECORD_TYPE_FILENAMES[record_type]
    return f"{record_type.rsplit('.', 1)[-1]}.csv"


def flush_run_metadata(
    storage: StorageManager,
    run_dir: Path,
    metadata: dict[str, Any],
) -> None:
    storage.write_run_metadata_atomic(run_dir, metadata)


def find_resume_run_dir(
    storage: StorageManager,
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


def stop_at_max_rows(
    metadata: dict[str, Any],
    storage: StorageManager,
    output_dir: Path,
    max_rows_int: int | None,
) -> bool:
    """Mark pending tasks skipped and flush when row cap is reached."""
    if max_rows_int is None or metadata["row_count"] < max_rows_int:
        return False
    mark_remaining_tasks_skipped(get_task_progress(metadata))
    flush_run_metadata(storage, output_dir, metadata)
    return True


def parse_max_rows(ingestion_params: dict[str, Any]) -> int | None:
    max_rows = ingestion_params.get("max_rows")
    return int(max_rows) if max_rows is not None else None


def build_base_sync_metadata(
    config: dict[str, Any],
    config_path: Path,
    sync_timestamp: str,
    sync_tasks: Sequence[TTask],
    *,
    task_progress_builder: Callable[[TTask], dict[str, Any]],
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "sync_status": SyncStatus.IN_PROGRESS.value,
        "dataset_id": require_dataset_id(config),
        "name": config["name"],
        "description": config["description"],
        "date": config["date"],
        "sync_timestamp": sync_timestamp,
        "ingestion_config": config_path.name,
        "record_types": config["record_types"],
        "ingestion_params": config["ingestion_params"],
        "row_count": 0,
        "tasks": {task.task_id: task_progress_builder(task) for task in sync_tasks},
    }
    if extra_fields:
        metadata.update(extra_fields)
    return metadata


def mark_task_in_progress(
    entry: dict[str, Any],
    storage: StorageManager,
    output_dir: Path,
    metadata: dict[str, Any],
) -> None:
    entry["status"] = TaskStatus.IN_PROGRESS.value
    entry["last_error"] = None
    flush_run_metadata(storage, output_dir, metadata)


def mark_task_failed(
    entry: dict[str, Any],
    exc: Exception,
    task_id: str,
    storage: StorageManager,
    output_dir: Path,
    metadata: dict[str, Any],
) -> None:
    entry["status"] = TaskStatus.FAILED.value
    entry["last_error"] = str(exc)
    flush_run_metadata(storage, output_dir, metadata)
    print(f"sync_records: {task_id} failed: {exc}")


def run_checkpointed_sync(
    sync_tasks: Sequence[TTask],
    metadata: dict[str, Any],
    storage: StorageManager,
    output_dir: Path,
    *,
    max_rows_int: int | None,
    tqdm_desc: str,
    process_task: Callable[[TTask, dict[str, Any]], None],
) -> None:
    progress = get_task_progress(metadata)

    for task in tqdm(
        sync_tasks,
        desc=tqdm_desc,
        disable=not sys.stderr.isatty(),
    ):
        entry = progress[task.task_id]
        if entry["status"] in (TaskStatus.COMPLETED.value, TaskStatus.SKIPPED.value):
            continue

        if stop_at_max_rows(metadata, storage, output_dir, max_rows_int):
            break

        process_task(task, entry)

        if stop_at_max_rows(metadata, storage, output_dir, max_rows_int):
            break

    metadata["sync_status"] = sync_status_from_tasks(progress).value
    flush_run_metadata(storage, output_dir, metadata)


def ensure_dataset_manifest(
    storage: StorageManager,
    platform: str,
    dataset_id: str,
    config: dict[str, Any],
    config_path: Path,
    *,
    repo_root: Path,
) -> None:
    manifest_path = storage.root_dir.parent / "dataset.json"
    if not manifest_path.exists():
        write_dataset_manifest(
            platform,
            dataset_id,
            name=str(config["name"]),
            ingestion_config=str(config_path.relative_to(repo_root)),
        )


def prepare_sync_run(
    storage: StorageManager,
    sync_tasks: Sequence[HasTaskId],
    *,
    resume: bool,
    run_dir_name: str | None,
    init_metadata_fn: Callable[[str], dict[str, Any]],
    entity_label: str,
) -> tuple[Path, dict[str, Any]]:
    if run_dir_name is not None and not resume:
        raise ValueError("--run-dir requires --resume")

    if resume:
        output_dir = find_resume_run_dir(storage, run_dir_name=run_dir_name)
        metadata = storage.load_run_metadata(output_dir)
        if metadata.get("sync_status") != SyncStatus.IN_PROGRESS.value:
            metadata["sync_status"] = SyncStatus.IN_PROGRESS.value
            flush_run_metadata(storage, output_dir, metadata)
        validate_tasks_for_resume(sync_tasks, metadata, entity_label=entity_label)
        print(f"sync_records: resuming {output_dir}")
        return output_dir, metadata

    sync_timestamp = get_current_timestamp()
    output_dir = storage.create_new_run_dir(sync_timestamp)
    metadata = init_metadata_fn(sync_timestamp)
    flush_run_metadata(storage, output_dir, metadata)
    print(f"sync_records: started new run {output_dir}")
    return output_dir, metadata


def run_sync_cli(
    *,
    configs_dir: Path,
    default_config: Path,
    sync_records_fn: Callable[..., Path],
    config_help: str,
) -> None:
    def main(
        config: Path = typer.Option(
            default_config,
            "--config",
            help=config_help,
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
        config_path = resolve_config_path(config, configs_dir)
        sync_records_fn(config_path, resume=resume, run_dir_name=run_dir)

    typer.run(main)
