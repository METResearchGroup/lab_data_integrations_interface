"""Preprocess Bluesky posts from raw CSV storage to filtered preprocessed output.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/preprocessing/preprocess_bluesky.py
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from data_platform.models.sync import SyncBlueskyPostModel
from data_platform.preprocessing.validators.validators import (
    check_if_not_phone,
    check_if_post_has_no_urls,
    check_if_text_english,
    check_if_valid_post_length,
)
from data_platform.utils.storage import BlueskyStorageManager

RAW_STORAGE = BlueskyStorageManager("raw")
PREPROCESSED_STORAGE = BlueskyStorageManager("preprocessed")
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


def load_posts() -> pd.DataFrame:
    """Load raw posts for preprocessing from the latest sync run."""
    posts = RAW_STORAGE.load_records(latest=True)
    if posts.empty:
        return posts.copy()

    return pd.DataFrame(_rows_to_validated_dicts(posts.to_dict(orient="records")))


def save_preprocessed_posts(posts: pd.DataFrame) -> Path:
    """Persist preprocessed posts to a new timestamped run directory."""
    output_dir = PREPROCESSED_STORAGE.create_new_run_dir()
    PREPROCESSED_STORAGE.write_records(posts.to_dict(orient="records"), output_dir)
    return output_dir


def preprocess_records() -> Path:
    posts = load_posts()
    preprocessed = run_preprocessing_pipeline(posts)
    output_dir = save_preprocessed_posts(preprocessed)
    print(
        f"preprocess_records: kept {len(preprocessed)} of {len(posts)} posts -> {output_dir}"
    )
    return output_dir


if __name__ == "__main__":
    preprocess_records()
