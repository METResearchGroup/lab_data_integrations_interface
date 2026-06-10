from __future__ import annotations

from pathlib import Path
from typing import Any

from data_platform.utils.storage import StorageManager


def load_prior_seen_ids(
    storage: StorageManager,
    output_dir: Path,
    fetch: dict[str, Any],
    id_column: str,
    *,
    filename: str | None = None,
    same_dataset_flag: str,
) -> set[str]:
    if fetch.get("dedupe_across_datasets", True):
        return storage.load_seen_ids_from_platform_raw_runs(
            output_dir, id_column, filename=filename
        )
    if fetch.get(same_dataset_flag):
        return storage.load_seen_ids_from_prior_runs(output_dir, id_column, filename=filename)
    return set()
