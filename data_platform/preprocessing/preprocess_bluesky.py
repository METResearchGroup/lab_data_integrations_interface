"""Preprocess Bluesky posts from raw CSV storage to filtered preprocessed output.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/preprocessing/preprocess_bluesky.py \\
        --dataset-id bluesky_<uuid>
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pandas as pd
import typer

from data_platform.models.sync import SyncBlueskyPostModel
from data_platform.preprocessing.validators.validators import (
    check_if_not_phone,
    check_if_post_has_no_urls,
    check_if_text_english,
    check_if_valid_post_length,
)
from data_platform.utils.dataset import dataset_root, relative_run_path, validate_dataset_id
from data_platform.utils.storage import BlueskyStorageManager

TEXT_COLUMN = "text"

TextValidator = Callable[[str], bool]

POST_TEXT_VALIDATORS: tuple[TextValidator, ...] = (
    check_if_not_phone,
    check_if_valid_post_length,
    check_if_post_has_no_urls,
    check_if_text_english,
)


def passes_all_validators(
    text: str,
    validators: Sequence[TextValidator] = POST_TEXT_VALIDATORS,
) -> bool:
    return all(validator(text) for validator in validators)


def filter_posts(
    posts: pd.DataFrame,
    validators: Sequence[TextValidator] = POST_TEXT_VALIDATORS,
) -> pd.DataFrame:
    """Return only posts whose text passes every validator in the pipeline."""
    if posts.empty:
        return posts.copy()

    mask = posts[TEXT_COLUMN].map(lambda value: passes_all_validators(str(value), validators))
    return posts.loc[mask].reset_index(drop=True)


def run_preprocessing_pipeline(
    posts: pd.DataFrame,
    validators: Sequence[TextValidator] = POST_TEXT_VALIDATORS,
) -> pd.DataFrame:
    return filter_posts(posts, validators)


def _rows_to_validated_dicts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [SyncBlueskyPostModel.model_validate(row).model_dump() for row in rows]


def load_posts(raw_storage: BlueskyStorageManager) -> pd.DataFrame:
    """Load raw posts for preprocessing from the latest sync run."""
    posts = raw_storage.load_records(latest=True)
    if posts.empty:
        return posts.copy()

    return pd.DataFrame(_rows_to_validated_dicts(posts.to_dict(orient="records")))


def save_preprocessed_posts(
    posts: pd.DataFrame,
    *,
    dataset_id: str,
    input_count: int,
) -> Path:
    """Persist preprocessed posts to a new timestamped run directory."""
    raw_storage = BlueskyStorageManager("raw", dataset_id)
    preprocessed_storage = BlueskyStorageManager("preprocessed", dataset_id)
    root = dataset_root("bluesky", dataset_id)

    output_dir = preprocessed_storage.create_new_run_dir()
    preprocessed_storage.write_records(posts.to_dict(orient="records"), output_dir)
    source_raw_run = raw_storage.latest_run_dir()
    metadata: dict[str, Any] = {
        "dataset_id": dataset_id,
        "source_raw_run": (
            relative_run_path(root, source_raw_run) if source_raw_run is not None else None
        ),
        "preprocess_timestamp": output_dir.name,
        "row_counts": {
            "input": input_count,
            "output": len(posts),
        },
        "files": {
            "posts": preprocessed_storage.records_filename,
        },
    }
    preprocessed_storage.write_run_metadata(output_dir, metadata)
    return output_dir


def preprocess_records(dataset_id: str) -> Path:
    dataset_id = validate_dataset_id(dataset_id)
    posts = load_posts(BlueskyStorageManager("raw", dataset_id))
    preprocessed = run_preprocessing_pipeline(posts)
    output_dir = save_preprocessed_posts(
        preprocessed, dataset_id=dataset_id, input_count=len(posts)
    )
    print(f"preprocess_records: kept {len(preprocessed)} of {len(posts)} posts -> {output_dir}")
    return output_dir


def main(
    dataset_id: str = typer.Option(
        ...,
        "--dataset-id",
        help="Dataset identifier from ingestion YAML (bluesky_<uuid>)",
    ),
) -> None:
    preprocess_records(dataset_id)


if __name__ == "__main__":
    typer.run(main)
