"""Shared checkpoint resume helpers for platform sync scripts."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol, TypeVar

from data_platform.utils.storage import StorageManager


class HasWorkItemKey(Protocol):
    @property
    def work_item_key(self) -> str: ...


T = TypeVar("T", bound=HasWorkItemKey)


def find_resume_run_dir(
    storage: StorageManager,
    *,
    run_dir_name: str | None,
) -> Path:
    """Return a requested run directory or the latest in-progress run directory."""
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
    work_items: Sequence[T],
    metadata: dict[str, Any],
    *,
    metadata_bucket: str,
    entity_label: str,
) -> list[T]:
    """Validate that config work items and resume metadata keys are identical."""
    work_item_keys = {item.work_item_key for item in work_items}
    metadata_keys = set(metadata.get(metadata_bucket, {}))
    missing = work_item_keys - metadata_keys
    extra = metadata_keys - work_item_keys
    if missing or extra:
        raise ValueError(
            f"Config {entity_label} do not match resume metadata "
            f"(missing in metadata: {sorted(missing)}, extra in metadata: {sorted(extra)})"
        )
    return list(work_items)


def flush_sync_metadata(storage: StorageManager, run_dir: Path, metadata: dict[str, Any]) -> None:
    """Persist sync metadata atomically to the run directory."""
    storage.write_run_metadata_atomic(run_dir, metadata)


def mark_remaining_skipped(metadata: dict[str, Any], *, metadata_bucket: str) -> None:
    """Mark every pending item in the metadata bucket as skipped."""
    for entry in metadata[metadata_bucket].values():
        if entry["status"] == "pending":
            entry["status"] = "skipped"


def sync_status_done(metadata: dict[str, Any], *, metadata_bucket: str) -> str:
    """Return completed only when all items are completed or skipped."""
    statuses = {entry["status"] for entry in metadata[metadata_bucket].values()}
    unfinished = statuses - {"completed", "skipped"}
    return "completed" if not unfinished else "in_progress"


def init_sync_metadata_base(
    config: dict[str, Any],
    config_path: Path,
    sync_timestamp: str,
    *,
    dataset_id: str,
    metadata_bucket: str,
    entries: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build base sync metadata with a platform-specific per-item status bucket."""
    metadata: dict[str, Any] = {
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
        metadata_bucket: entries,
    }
    if extra:
        metadata.update(extra)
    return metadata
