"""Generate features for preprocessed Bluesky posts.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/generate_features/generate_bluesky_features.py \\
        --dataset-id bluesky_<uuid> --batch-size 64
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import typer
from pydantic import BaseModel

from data_platform.aws.constants import S3_BUCKET
from data_platform.aws.s3 import S3
from data_platform.generate_features.generate_features import FeatureGenerationConfig
from data_platform.generate_features.metadata import flush_metadata, metadata_path
from data_platform.generate_features.models import FeatureRunConfig, FeatureRunMetadata
from data_platform.generate_features.platform_cli import (
    features_from_cli,
    generate_feature_subset,
    run_feature_generation,
)
from data_platform.generate_features.registry import FEATURE_REGISTRY
from data_platform.models.sync import SyncBlueskyPostModel
from data_platform.utils.dataset import dataset_root, validate_dataset_id
from data_platform.utils.feature_labels import FeatureLabelQuery
from data_platform.utils.platform_ids import BLUESKY_BINDING
from data_platform.utils.storage import BlueskyStorageManager, StorageManager, StorageStage


def bluesky_feature_config(
    dataset_id: str,
    *,
    run_config: FeatureRunConfig,
    preprocessed_run: str | None = None,
    features_subset: tuple[str, ...] | None = None,
) -> FeatureGenerationConfig:
    """Build a FeatureGenerationConfig for Bluesky flat feature CSV output."""
    dataset_id = validate_dataset_id(dataset_id)
    registry = FEATURE_REGISTRY
    if features_subset:
        registry = {name: FEATURE_REGISTRY[name] for name in features_subset}

    binding = BLUESKY_BINDING
    feature_label_storage = StorageManager(
        "bluesky",
        StorageStage.FEATURES,
        BaseModel,
        dataset_id,
        records_filename="features",
    )
    return FeatureGenerationConfig(
        platform="bluesky",
        id_column=binding.records_id_column,
        text_column=binding.text_column,
        feature_registry=registry,
        input_storage=BlueskyStorageManager(StorageStage.PREPROCESSED, dataset_id),
        features_dir=feature_label_storage.root_dir,
        feature_label_query=FeatureLabelQuery(
            feature_storage=feature_label_storage,
            id_column=binding.records_id_column,
        ),
        run_config=run_config,
        preprocessed_run=preprocessed_run,
    )


def load_posts(dataset_id: str, preprocessed_run: str | None = None) -> pd.DataFrame:
    """Load preprocessed posts from the latest or a pinned preprocessing run."""
    storage = BlueskyStorageManager(StorageStage.PREPROCESSED, dataset_id)
    if preprocessed_run:
        run_dir = dataset_root("bluesky", dataset_id) / preprocessed_run
        posts = storage.load_records(run_dir)
    else:
        posts = storage.load_records(latest=True)
    if posts.empty:
        return posts.copy()

    return pd.DataFrame(
        SyncBlueskyPostModel.model_validate(row).model_dump()
        for row in posts.to_dict(orient="records")
    )


def generate_bluesky_features(
    dataset_id: str,
    *,
    batch_size: int = 64,
    max_concurrency: int = 80,
    opik_enabled: bool = False,
    preprocessed_run: str | None = None,
    feature_subset: list[str] | None = None,
) -> dict[str, Path]:
    """Load Bluesky posts and generate the requested feature labels."""
    dataset_id = validate_dataset_id(dataset_id)

    preprocessed_storage = BlueskyStorageManager(StorageStage.PREPROCESSED, dataset_id)
    latest_preprocessed_run = preprocessed_storage.latest_run_dir()
    if latest_preprocessed_run is None:
        raise FileNotFoundError(f"No preprocessed runs found for dataset {dataset_id}")
    preprocessed_meta = preprocessed_storage.load_run_metadata(latest_preprocessed_run)
    if not preprocessed_meta.get("s3_upload_status"):
        raise RuntimeError(
            f"Latest preprocessed run {latest_preprocessed_run.name} has not been uploaded to S3"
        )

    features_subset = generate_feature_subset(feature_subset)
    run_config = FeatureRunConfig(
        batch_size=batch_size,
        max_concurrency=max_concurrency,
        opik_enabled=opik_enabled,
    )
    posts = load_posts(dataset_id, preprocessed_run)
    config = bluesky_feature_config(
        dataset_id,
        run_config=run_config,
        preprocessed_run=preprocessed_run,
        features_subset=features_subset,
    )
    written = run_feature_generation(
        posts,
        config,
        empty_message="generate_bluesky_features: no preprocessed posts found",
    )

    if written:
        meta_file = metadata_path(config.features_dir)
        with meta_file.open(encoding="utf-8") as f:
            run_metadata = FeatureRunMetadata.from_dict(json.load(f))
        if run_metadata.sync_status == "completed":
            for _, path in written.items():
                key = f"features/platform=bluesky/dataset_id={dataset_id}/{path.name}"
                S3().upload_file(path, S3_BUCKET, key)
                print(f"generate_bluesky_features: uploaded features to s3://{S3_BUCKET}/{key}")
            run_metadata.s3_upload_status = True
            flush_metadata(config.features_dir, run_metadata)

    return written


def main(
    dataset_id: str = typer.Option(
        ...,
        "--dataset-id",
        help="Dataset identifier from ingestion YAML (bluesky_<uuid>)",
    ),
    batch_size: int = typer.Option(64, "--batch-size"),
    max_concurrency: int = typer.Option(80, "--max-concurrency"),
    opik_enabled: bool = typer.Option(False, "--opik", help="Enable Opik telemetry"),
    preprocessed_run: str | None = typer.Option(
        None,
        "--preprocessed-run",
        help="Pin preprocessed run path, e.g. preprocessed/2026_05_29-20:14:22",
    ),
    features: list[str] | None = typer.Option(
        None,
        "--features",
        help="Feature name(s); repeat the flag per feature, e.g. --features is_political",
    ),
) -> None:
    """CLI entrypoint for resumable Bluesky feature generation."""
    generate_bluesky_features(
        dataset_id,
        batch_size=batch_size,
        max_concurrency=max_concurrency,
        opik_enabled=opik_enabled,
        preprocessed_run=preprocessed_run,
        feature_subset=features_from_cli(features),
    )


if __name__ == "__main__":
    typer.run(main)
