"""Preprocess Reddit comments from raw CSV storage to filtered preprocessed output.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/preprocessing/preprocess_reddit.py \\
        --dataset-id reddit_<uuid>
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pandas as pd
import typer

from data_platform.models.sync import SyncRedditCommentModel
from data_platform.preprocessing.validators.reddit_validators import (
    check_if_body_not_removed,
    check_if_no_direct_urls,
    check_if_no_markdown_links,
    check_if_no_media_hosts,
    check_if_no_reddit_mentions,
    check_if_not_automoderator,
)
from data_platform.preprocessing.validators.validators import (
    check_if_not_phone,
    check_if_text_english,
)
from data_platform.utils.dataset import dataset_root, relative_run_path, validate_dataset_id
from data_platform.utils.storage import RedditStorageManager

TEXT_COLUMN = "body"
AUTHOR_COLUMN = "author"

TextValidator = Callable[[str], bool]
RowValidator = Callable[[str], bool]

COMMENT_TEXT_VALIDATORS: tuple[TextValidator, ...] = (
    check_if_body_not_removed,
    check_if_no_reddit_mentions,
    check_if_no_markdown_links,
    check_if_no_direct_urls,
    check_if_no_media_hosts,
    check_if_not_phone,
    check_if_text_english,
)

COMMENT_ROW_VALIDATORS: tuple[RowValidator, ...] = (check_if_not_automoderator,)


def passes_all_validators(
    text: str,
    validators: Sequence[TextValidator] = COMMENT_TEXT_VALIDATORS,
) -> bool:
    return all(validator(text) for validator in validators)


def passes_row_validators(
    author: str,
    validators: Sequence[RowValidator] = COMMENT_ROW_VALIDATORS,
) -> bool:
    return all(validator(author) for validator in validators)


def filter_comments(
    comments: pd.DataFrame,
    text_validators: Sequence[TextValidator] = COMMENT_TEXT_VALIDATORS,
    row_validators: Sequence[RowValidator] = COMMENT_ROW_VALIDATORS,
) -> pd.DataFrame:
    """Return only comments whose body and author pass every validator."""
    if comments.empty:
        return comments.copy()

    text_mask = comments[TEXT_COLUMN].map(
        lambda value: passes_all_validators(str(value), text_validators)
    )
    author_mask = comments[AUTHOR_COLUMN].map(
        lambda value: passes_row_validators(str(value), row_validators)
    )
    return comments.loc[text_mask & author_mask].reset_index(drop=True)


def run_preprocessing_pipeline(
    comments: pd.DataFrame,
    text_validators: Sequence[TextValidator] = COMMENT_TEXT_VALIDATORS,
    row_validators: Sequence[RowValidator] = COMMENT_ROW_VALIDATORS,
) -> pd.DataFrame:
    return filter_comments(comments, text_validators, row_validators)


def _rows_to_validated_dicts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [SyncRedditCommentModel.model_validate(row).model_dump() for row in rows]


def load_comments(raw_storage: RedditStorageManager) -> pd.DataFrame:
    """Load raw comments for preprocessing from the latest sync run."""
    comments = raw_storage.load_records(latest=True)
    if comments.empty:
        return comments.copy()

    return pd.DataFrame(_rows_to_validated_dicts(comments.to_dict(orient="records")))


def save_preprocessed_comments(
    comments: pd.DataFrame,
    *,
    dataset_id: str,
    input_count: int,
) -> Path:
    """Persist preprocessed comments to a new timestamped run directory."""
    raw_storage = RedditStorageManager("raw", dataset_id)
    preprocessed_storage = RedditStorageManager("preprocessed", dataset_id)
    root = dataset_root("reddit", dataset_id)

    output_dir = preprocessed_storage.create_new_run_dir()
    preprocessed_storage.write_records(comments.to_dict(orient="records"), output_dir)
    source_raw_run = raw_storage.latest_run_dir()
    metadata: dict[str, Any] = {
        "dataset_id": dataset_id,
        "source_raw_run": (
            relative_run_path(root, source_raw_run) if source_raw_run is not None else None
        ),
        "preprocess_timestamp": output_dir.name,
        "row_counts": {
            "input": input_count,
            "output": len(comments),
        },
        "files": {
            "comments": preprocessed_storage.records_filename,
        },
    }
    preprocessed_storage.write_run_metadata(output_dir, metadata)
    return output_dir


def preprocess_records(dataset_id: str) -> Path:
    dataset_id = validate_dataset_id(dataset_id)
    comments = load_comments(RedditStorageManager("raw", dataset_id))
    preprocessed = run_preprocessing_pipeline(comments)
    output_dir = save_preprocessed_comments(
        preprocessed, dataset_id=dataset_id, input_count=len(comments)
    )
    print(
        f"preprocess_records: kept {len(preprocessed)} of {len(comments)} comments -> {output_dir}"
    )
    return output_dir


def main(
    dataset_id: str = typer.Option(
        ...,
        "--dataset-id",
        help="Dataset identifier from ingestion YAML (reddit_<uuid>)",
    ),
) -> None:
    preprocess_records(dataset_id)


if __name__ == "__main__":
    typer.run(main)
