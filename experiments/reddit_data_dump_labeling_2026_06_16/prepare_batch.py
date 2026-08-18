from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd
import typer

from experiments.reddit_data_dump_labeling_2026_06_16.patch_data_root import patch_data_root

patch_data_root()

from data_platform.models.sync import SyncRedditCommentModel
from data_platform.utils.dataset import ValidDataFormats, write_dataset_manifest
from data_platform.utils.storage import RedditStorageManager
from experiments.reddit_data_dump_labeling_2026_06_16.paths import (
    EXPERIMENT_ROOT,
    dataset_id_for,
    parquet_path_for,
)
from lib.timestamp_utils import get_current_timestamp

COMMENT_FIELDS = list(SyncRedditCommentModel.model_fields.keys())
PROB_TOXIC_COLUMN = "prob_toxic"


def _validate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    for row in rows:
        validated.append(SyncRedditCommentModel.model_validate(row).model_dump())
    return validated


def prepare_batch(
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

    if PROB_TOXIC_COLUMN in df.columns:
        df = df.drop(columns=[PROB_TOXIC_COLUMN])

    rows = _validate_rows(df.to_dict(orient="records"))
    dataset_id = dataset_id_for(batch)
    storage = RedditStorageManager("preprocessed", dataset_id)
    run_dir = storage.create_new_run_dir(get_current_timestamp())
    output_path = run_dir / storage.records_filename

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COMMENT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    write_dataset_manifest(
        "reddit",
        dataset_id,
        name=f"pushshift_{batch}",
        ingestion_config=f"experiments/reddit_data_dump_labeling_2026_06_16/batches.yaml#{batch}",
        format=ValidDataFormats.CSV,
    )

    metadata = {
        "dataset_id": dataset_id,
        "source_batch": batch,
        "source_parquet": str(parquet_path.relative_to(experiment_root or EXPERIMENT_ROOT)),
        "preprocess_timestamp": run_dir.name,
        "row_counts": {"input": len(df), "output": len(rows)},
        "files": {"comments": storage.records_filename},
    }
    storage.write_run_metadata(run_dir, metadata)
    return output_path


def main(
    batch: str = typer.Option(..., "--batch", help="Batch key from batches.yaml"),
    limit: int | None = typer.Option(None, "--limit", help="Optional row cap for pilot runs"),
) -> None:
    output_path = prepare_batch(batch, limit=limit)
    print(f"prepare_batch: wrote {output_path}")


if __name__ == "__main__":
    typer.run(main)
