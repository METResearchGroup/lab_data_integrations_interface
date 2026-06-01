"""Preprocess Bluesky posts from raw CSV storage to filtered preprocessed output.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/preprocessing/preprocess_bluesky.py \\
        --dataset-id bluesky_<uuid>
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pandas as pd
import typer

from data_platform.models.sync import SyncBlueskyPostModel
from data_platform.preprocessing.runner import (
    PreprocessPlatformSpec,
    TextValidator,
    filter_records,
    passes_all_validators,
    preprocess_records as run_preprocess_records,
)
from data_platform.preprocessing.validators.validators import (
    check_if_not_phone,
    check_if_post_has_no_urls,
    check_if_text_english,
    check_if_valid_post_length,
)
from data_platform.utils.platform_ids import BLUESKY_BINDING
from data_platform.utils.storage import BlueskyStorageManager

POST_TEXT_VALIDATORS: tuple[TextValidator, ...] = (
    check_if_not_phone,
    check_if_valid_post_length,
    check_if_post_has_no_urls,
    check_if_text_english,
)

BLUESKY_SPEC = PreprocessPlatformSpec(
    platform="bluesky",
    storage_cls=BlueskyStorageManager,
    model_cls=SyncBlueskyPostModel,
    binding=BLUESKY_BINDING,
    text_validators=POST_TEXT_VALIDATORS,
)


def filter_posts(
    posts: pd.DataFrame,
    validators: Sequence[TextValidator] = POST_TEXT_VALIDATORS,
) -> pd.DataFrame:
    spec = PreprocessPlatformSpec(
        platform=BLUESKY_SPEC.platform,
        storage_cls=BLUESKY_SPEC.storage_cls,
        model_cls=BLUESKY_SPEC.model_cls,
        binding=BLUESKY_SPEC.binding,
        text_validators=tuple(validators),
    )
    return filter_records(posts, spec)


def preprocess_records(dataset_id: str) -> Path:
    return run_preprocess_records(dataset_id, BLUESKY_SPEC)


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
