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

from data_platform.aws.constants import S3_BUCKET
from data_platform.aws.s3 import S3
from data_platform.models.sync import SyncBlueskyPostModel
from data_platform.preprocessing.runner import (
    PreprocessPlatformSpec,
    TextValidator,
    filter_records,
)
from data_platform.preprocessing.runner import (
    preprocess_records as run_preprocess_records,
)
from data_platform.preprocessing.validators.validators import (
    check_if_not_phone,
    check_if_post_has_no_urls,
    check_if_text_english,
    check_if_valid_post_length,
)
from data_platform.utils.platform_ids import BLUESKY_BINDING
from data_platform.utils.storage import BlueskyStorageManager, StorageStage

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
    output_dir = run_preprocess_records(dataset_id, BLUESKY_SPEC)
    preprocessed_storage = BlueskyStorageManager(StorageStage.PREPROCESSED, dataset_id)
    csv_filename = preprocessed_storage.records_filename
    key = (
        f"preprocessed/platform=bluesky/dataset_id={dataset_id}"
        f"/run_dir={output_dir.name}/{csv_filename}"
    )
    S3().upload_file(output_dir / csv_filename, S3_BUCKET, key)
    print(f"preprocess_records: uploaded preprocessed to s3://{S3_BUCKET}/{key}")
    metadata = preprocessed_storage.load_run_metadata(output_dir)
    metadata["s3_upload_status"] = True
    preprocessed_storage.write_run_metadata(output_dir, metadata)
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
