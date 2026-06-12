from __future__ import annotations

from pathlib import Path
from typing import Any

from data_platform.utils.storage import StorageManager


def load_prior_seen_ids(
    storage: StorageManager,
    output_dir: Path,
    ingestion_params: dict[str, Any],
    id_column: str,
    *,
    filename: str | None = None,
    same_dataset_flag: str,
) -> set[str]:
    if ingestion_params.get("dedupe_across_datasets", True):
        return storage.load_seen_ids_from_platform_raw_runs(
            output_dir, id_column, filename=filename
        )
    if ingestion_params.get(same_dataset_flag):
        return storage.load_seen_ids_from_prior_runs(output_dir, id_column, filename=filename)
    return set()


def append_deduped_rows(
    storage: StorageManager,
    output_dir: Path,
    rows: list[dict[str, Any]],
    id_column: str,
    *,
    prior_ids: set[str],
    filename: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Append rows not already seen. Returns (new_rows, skipped_count)."""
    seen_ids = prior_ids | storage.load_seen_ids(output_dir, id_column, filename=filename)
    new_rows = [row for row in rows if row[id_column] not in seen_ids]
    skipped = len(rows) - len(new_rows)
    if new_rows:
        storage.append_records(new_rows, output_dir, filename=filename)
    return new_rows, skipped
