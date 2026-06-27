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

from data_platform.aws.athena import Athena
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
from data_platform.utils.dataset import validate_dataset_id
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


def _publish_preprocessed_run(dataset_id: str, run_dir: Path, csv_path: Path) -> None:
    """Upload a preprocessed CSV to S3 and register its Athena partition."""
    s3_prefix = f"preprocessed/platform=bluesky/dataset_id={dataset_id}/run_dir={run_dir.name}"
    s3_key = f"{s3_prefix}/{csv_path.name}"
    S3().upload_file(csv_path, S3_BUCKET, s3_key)
    Athena().register_partition(
        "bluesky_preprocessed",
        {"platform": "bluesky", "dataset_id": dataset_id, "run_dir": run_dir.name},
        f"s3://{S3_BUCKET}/{s3_prefix}/",
    )
    print(f"preprocess_records: uploaded to s3://{S3_BUCKET}/{s3_key}")
    print(
        f"preprocess_records: registered partition bluesky_preprocessed"
        f" platform=bluesky dataset_id={dataset_id} run_dir={run_dir.name}"
    )


def _retry_pending_uploads(dataset_id: str, preprocessed_storage: BlueskyStorageManager) -> None:
    """Retry S3 upload for any preprocessed run dirs that completed but failed to upload."""
    if not preprocessed_storage.root_dir.exists():
        return
    csv_filename = preprocessed_storage.records_filename
    for run_dir in sorted(preprocessed_storage.root_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        metadata = preprocessed_storage.load_run_metadata(run_dir)
        if metadata.get("s3_upload_status", False):
            continue
        csv_path = run_dir / csv_filename
        if not csv_path.exists():
            continue
        _publish_preprocessed_run(dataset_id, run_dir, csv_path)
        metadata["s3_upload_status"] = True
        preprocessed_storage.write_run_metadata(run_dir, metadata)


def preprocess_records(dataset_id: str) -> Path | None:
    dataset_id = validate_dataset_id(dataset_id)
    preprocessed_storage = BlueskyStorageManager(StorageStage.PREPROCESSED, dataset_id)
    _retry_pending_uploads(dataset_id, preprocessed_storage)

    output_dir = run_preprocess_records(dataset_id, BLUESKY_SPEC)
    if output_dir is None:
        return None

    csv_filename = preprocessed_storage.records_filename
    _publish_preprocessed_run(dataset_id, output_dir, output_dir / csv_filename)

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
