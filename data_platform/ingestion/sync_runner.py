"""Shared sync_records orchestration for platform ingestion scripts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer

from data_platform.ingestion.sync_checkpoint import (
    find_resume_run_dir,
    flush_sync_metadata,
    merge_work_items_with_metadata,
)
from data_platform.utils.config_paths import load_yaml_config, resolve_config_path
from data_platform.utils.dataset import validate_dataset_id, write_dataset_manifest
from data_platform.utils.storage import StorageManager
from lib.timestamp_utils import get_current_timestamp


def validate_run_dir_option(run_dir_name: str | None, *, resume: bool) -> None:
    """Reject --run-dir unless --resume is also set."""
    if run_dir_name is not None and not resume:
        raise ValueError("--run-dir requires --resume")


def require_dataset_id(config: dict[str, Any], *, hint: str) -> str:
    """Return a validated dataset_id from ingestion config."""
    raw = config.get("dataset_id")
    if not raw:
        raise ValueError(f"ingestion config must include dataset_id ({hint})")
    return validate_dataset_id(str(raw))


def ensure_dataset_manifest(
    platform: str,
    storage: StorageManager,
    config: dict[str, Any],
    config_path: Path,
) -> None:
    """Write dataset.json once when missing for this dataset root."""
    manifest_path = storage.root_dir.parent / "dataset.json"
    if manifest_path.exists():
        return
    repo_root = Path(__file__).resolve().parents[2]
    write_dataset_manifest(
        platform,
        storage.dataset_id,
        name=str(config["name"]),
        ingestion_config=str(config_path.relative_to(repo_root)),
    )


@dataclass
class PreparedSyncRun:
    storage: StorageManager
    output_dir: Path
    metadata: dict[str, Any]
    work_items: list[Any]
    config: dict[str, Any]
    config_path: Path
    fetch: dict[str, Any]
    sync_timestamp: str


def prepare_sync_run(
    storage: StorageManager,
    config: dict[str, Any],
    config_path: Path,
    work_items: list[Any],
    *,
    resume: bool,
    run_dir_name: str | None,
    metadata_bucket: str,
    entity_label: str,
    init_sync_metadata: Callable[[dict[str, Any], Path, str, list[Any]], dict[str, Any]],
) -> PreparedSyncRun:
    """Create or resume a raw run directory and return prepared sync state."""
    fetch = config["fetch"]
    if resume:
        output_dir = find_resume_run_dir(storage, run_dir_name=run_dir_name)
        metadata = storage.load_run_metadata(output_dir)
        if metadata.get("sync_status") != "in_progress":
            metadata["sync_status"] = "in_progress"
            flush_sync_metadata(storage, output_dir, metadata)
        work_items = merge_work_items_with_metadata(
            work_items,
            metadata,
            metadata_bucket=metadata_bucket,
            entity_label=entity_label,
        )
        sync_timestamp = str(metadata["sync_timestamp"])
        print(f"sync_records: resuming {output_dir}")
    else:
        sync_timestamp = get_current_timestamp()
        output_dir = storage.create_new_run_dir(sync_timestamp)
        metadata = init_sync_metadata(config, config_path, sync_timestamp, work_items)
        flush_sync_metadata(storage, output_dir, metadata)
        print(f"sync_records: started new run {output_dir}")
    return PreparedSyncRun(
        storage=storage,
        output_dir=output_dir,
        metadata=metadata,
        work_items=work_items,
        config=config,
        config_path=config_path,
        fetch=fetch,
        sync_timestamp=sync_timestamp,
    )


@dataclass(frozen=True)
class SyncPlatformSpec:
    platform: str
    dataset_id_hint: str
    metadata_bucket: str
    entity_label: str
    create_storage: Callable[[str], StorageManager]
    iter_work_items: Callable[[dict[str, Any]], list[Any]]
    init_sync_metadata: Callable[[dict[str, Any], Path, str, list[Any]], dict[str, Any]]
    run_loop: Callable[[PreparedSyncRun], None]


def run_sync_from_config(
    config_path: Path,
    *,
    resume: bool = False,
    run_dir_name: str | None = None,
    spec: SyncPlatformSpec,
) -> Path:
    """Run manifest setup, resume/new branch, platform loop, and completion logging."""
    validate_run_dir_option(run_dir_name, resume=resume)
    config = load_yaml_config(config_path)
    dataset_id = require_dataset_id(config, hint=spec.dataset_id_hint)
    storage = spec.create_storage(dataset_id)
    ensure_dataset_manifest(spec.platform, storage, config, config_path)
    work_items = spec.iter_work_items(config["fetch"])
    prepared = prepare_sync_run(
        storage,
        config,
        config_path,
        work_items,
        resume=resume,
        run_dir_name=run_dir_name,
        metadata_bucket=spec.metadata_bucket,
        entity_label=spec.entity_label,
        init_sync_metadata=spec.init_sync_metadata,
    )
    spec.run_loop(prepared)
    total_rows = prepared.metadata["row_count"]
    print(
        f"sync_records: wrote {total_rows} rows to {prepared.output_dir} "
        f"(status={prepared.metadata['sync_status']})"
    )
    return prepared.output_dir


def make_sync_main(
    *,
    sync_records: Callable[..., Path],
    configs_dir: Path,
    default_config: Path,
    config_help_subdir: str,
) -> Callable[..., None]:
    """Build a Typer CLI entrypoint for a platform sync script."""

    def main(
        config: Path = typer.Option(
            default_config,
            "--config",
            help=(
                f"YAML config path or filename under configs/{config_help_subdir}/ "
                "(e.g. mirrorview.yaml)"
            ),
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
        sync_records(config_path, resume=resume, run_dir_name=run_dir)

    return main
