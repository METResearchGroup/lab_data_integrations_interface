"""Preprocess Reddit comments from raw CSV storage to filtered preprocessed output.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/preprocessing/preprocess_reddit.py \\
        --dataset-id reddit_<uuid>
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pandas as pd
import typer

from data_platform.models.sync import SyncRedditCommentModel

from data_platform.preprocessing.runner import (
    PreprocessPlatformSpec,
    RowValidator,
    TextValidator,
    filter_records,
    passes_all_validators as _passes_all_validators,
    passes_row_validators as _passes_row_validators,
    preprocess_records as run_preprocess_records,
)
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
from data_platform.utils.platform_ids import REDDIT_BINDING
from data_platform.utils.storage import RedditStorageManager

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

REDDIT_SPEC = PreprocessPlatformSpec(
    platform="reddit",
    storage_cls=RedditStorageManager,
    model_cls=SyncRedditCommentModel,
    binding=REDDIT_BINDING,
    text_validators=COMMENT_TEXT_VALIDATORS,
    row_validators=COMMENT_ROW_VALIDATORS,
)


def passes_all_validators(
    text: str,
    validators: Sequence[TextValidator] = COMMENT_TEXT_VALIDATORS,
) -> bool:
    return _passes_all_validators(text, validators)


def passes_row_validators(
    author: str,
    validators: Sequence[RowValidator] = COMMENT_ROW_VALIDATORS,
) -> bool:
    return _passes_row_validators(author, validators)


def filter_comments(
    comments: pd.DataFrame,
    text_validators: Sequence[TextValidator] = COMMENT_TEXT_VALIDATORS,
    row_validators: Sequence[RowValidator] = COMMENT_ROW_VALIDATORS,
) -> pd.DataFrame:
    spec = PreprocessPlatformSpec(
        platform=REDDIT_SPEC.platform,
        storage_cls=REDDIT_SPEC.storage_cls,
        model_cls=REDDIT_SPEC.model_cls,
        binding=REDDIT_SPEC.binding,
        text_validators=tuple(text_validators),
        row_validators=tuple(row_validators),
    )
    return filter_records(comments, spec)


def preprocess_records(dataset_id: str) -> Path:
    return run_preprocess_records(dataset_id, REDDIT_SPEC)


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
