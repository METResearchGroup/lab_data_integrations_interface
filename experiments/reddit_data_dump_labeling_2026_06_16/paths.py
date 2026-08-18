from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

EXPERIMENT_ROOT = Path(__file__).resolve().parent
EXPERIMENT_DATA_ROOT = EXPERIMENT_ROOT / "data"
BATCHES_PATH = EXPERIMENT_ROOT / "batches.yaml"


def load_batches() -> dict[str, dict[str, str]]:
    with BATCHES_PATH.open(encoding="utf-8") as f:
        batches = yaml.safe_load(f)
    if not isinstance(batches, dict):
        raise ValueError(f"Invalid batches config: {BATCHES_PATH}")
    return batches


def batch_config(batch: str) -> dict[str, str]:
    batches = load_batches()
    if batch not in batches:
        known = ", ".join(sorted(batches))
        raise KeyError(f"Unknown batch {batch!r}; expected one of: {known}")
    return batches[batch]


def parquet_path_for(batch: str, *, experiment_root: Path | None = None) -> Path:
    config = batch_config(batch)
    root = experiment_root or EXPERIMENT_ROOT
    return root / config["parquet"]


def dataset_id_for(batch: str) -> str:
    return batch_config(batch)["dataset_id"]


def dataset_root_for(batch: str, *, data_root: Path | None = None) -> Path:
    root = data_root or EXPERIMENT_DATA_ROOT
    return root / "reddit" / dataset_id_for(batch)
