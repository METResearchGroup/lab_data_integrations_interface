from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd
import typer

from experiments.reddit_data_dump_labeling_2026_06_16.patch_data_root import patch_data_root

patch_data_root()

from data_platform.generate_features.is_toxic_tiered.generate_feature import (
    IsToxicTieredModel,
    toxicity_tier_from_prob,
)
from data_platform.utils.storage import StorageManager
from experiments.reddit_data_dump_labeling_2026_06_16.paths import (
    dataset_id_for,
    parquet_path_for,
)
from lib.timestamp_utils import get_current_timestamp

FEATURE_NAME = "is_toxic_tiered"
PROB_TOXIC_COLUMN = "prob_toxic"
FEATURE_FIELDS = list(IsToxicTieredModel.model_fields.keys())


def _rows_from_parquet(df: pd.DataFrame) -> list[dict[str, Any]]:
    if PROB_TOXIC_COLUMN not in df.columns:
        raise ValueError(f"Parquet missing required column: {PROB_TOXIC_COLUMN}")

    label_timestamp = get_current_timestamp()
    rows: list[dict[str, Any]] = []
    for record in df.to_dict(orient="records"):
        prob = float(record[PROB_TOXIC_COLUMN])
        row = IsToxicTieredModel(
            uri=str(record["comment_fullname"]),
            label_timestamp=label_timestamp,
            toxicity_prob=prob,
            toxicity_tier=toxicity_tier_from_prob(prob),
        )
        rows.append(row.model_dump())
    return rows


def _write_feature_metadata(
    features_dir: Path,
    *,
    dataset_id: str,
    labeled: int,
) -> None:
    metadata = {
        "dataset_id": dataset_id,
        "source_preprocessed_run": None,
        "sync_status": "in_progress",
        "features": {
            FEATURE_NAME: {
                "status": "completed",
                "labeled": labeled,
                "failed_batches": 0,
            }
        },
        "config": {},
        "updated_at": get_current_timestamp(),
    }
    features_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = features_dir / "metadata.json"
    if metadata_path.exists():
        with metadata_path.open(encoding="utf-8") as f:
            existing = json.load(f)
        existing.setdefault("features", {})[FEATURE_NAME] = metadata["features"][FEATURE_NAME]
        existing["updated_at"] = metadata["updated_at"]
        metadata = existing

    with metadata_path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)


def seed_toxicity_features(
    batch: str,
    *,
    limit: int | None = None,
    experiment_root: Path | None = None,
    data_root: Path | None = None,
) -> Path:
    if data_root is not None:
        patch_data_root(data_root)

    parquet_path = parquet_path_for(batch, experiment_root=experiment_root)
    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet not found: {parquet_path}")

    df = pd.read_parquet(parquet_path)
    if limit is not None:
        df = df.head(limit)

    rows = _rows_from_parquet(df)
    dataset_id = dataset_id_for(batch)
    feature_storage = StorageManager(
        "reddit",
        "features",
        IsToxicTieredModel,
        dataset_id,
        records_filename=FEATURE_NAME,
    )
    feature_storage.root_dir.mkdir(parents=True, exist_ok=True)
    output_path = feature_storage.root_dir / feature_storage.records_filename

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FEATURE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    _write_feature_metadata(feature_storage.root_dir, dataset_id=dataset_id, labeled=len(rows))
    return output_path


def main(
    batch: str = typer.Option(..., "--batch", help="Batch key from batches.yaml"),
    limit: int | None = typer.Option(None, "--limit", help="Optional row cap for pilot runs"),
) -> None:
    output_path = seed_toxicity_features(batch, limit=limit)
    print(f"seed_toxicity_features: wrote {output_path}")


if __name__ == "__main__":
    typer.run(main)
