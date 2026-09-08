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

from data_platform.aws.athena import Athena
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
from data_platform.generate_features.registry import (
    FEATURE_REGISTRY,
    default_feature_registry,
)
from data_platform.models.sync import SyncBlueskyPostModel
from data_platform.utils.dataset import dataset_root, validate_dataset_id
from data_platform.utils.feature_labels import FeatureLabelQuery
from data_platform.utils.gate_checks import require_all_runs_uploaded
from data_platform.utils.platform_ids import BLUESKY_BINDING
from data_platform.utils.storage import BlueskyStorageManager, StorageManager, StorageStage


def bluesky_feature_config(
    dataset_id: str,
    *,
    run_config: FeatureRunConfig,
    features_subset: tuple[str, ...] | None = None,
) -> FeatureGenerationConfig:
    """Build a FeatureGenerationConfig for Bluesky flat feature CSV output."""
    dataset_id = validate_dataset_id(dataset_id)
    registry = (
        {name: FEATURE_REGISTRY[name] for name in features_subset}
        if features_subset
        else default_feature_registry()
    )

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
    )


def _publish_feature(dataset_id: str, feature_name: str, local_path: Path) -> None:
    """Upload a feature parquet file to S3 and register its Athena partition."""
    s3_prefix = f"features/platform=bluesky/feature={feature_name}/dataset_id={dataset_id}"
    s3_key = f"{s3_prefix}/{local_path.name}"
    S3().upload_file(local_path, S3_BUCKET, s3_key)
    Athena().register_partition(
        f"bluesky_features_{feature_name}",
        {"platform": "bluesky", "dataset_id": dataset_id},
        f"s3://{S3_BUCKET}/{s3_prefix}/",
    )
    print(f"generate_bluesky_features: uploaded {feature_name} -> s3://{S3_BUCKET}/{s3_key}")
    print(
        f"generate_bluesky_features: registered partition bluesky_features_{feature_name}"
        f" platform=bluesky dataset_id={dataset_id}"
    )


def _retry_pending_upload(dataset_id: str, features_dir: Path) -> None:
    """Retry S3 upload if features are complete but not yet uploaded."""
    meta_file = metadata_path(features_dir)
    if not meta_file.exists():
        return
    with meta_file.open(encoding="utf-8") as f:
        meta = FeatureRunMetadata.from_dict(json.load(f))
    if meta.sync_status != "completed" or meta.s3_upload_status:
        return
    feature_files = sorted(f for ext in ("*.parquet", "*.csv") for f in features_dir.glob(ext))
    for feature_file in feature_files:
        _publish_feature(dataset_id, feature_file.stem, feature_file)
    meta.s3_upload_status = True
    flush_metadata(features_dir, meta)


def load_all_posts(dataset_id: str) -> pd.DataFrame:
    """Load preprocessed posts from all preprocessed run dirs."""
    storage = BlueskyStorageManager(StorageStage.PREPROCESSED, dataset_id)
    all_rows = []
    for run_dir in sorted(storage.root_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        posts = storage.load_records(run_dir=run_dir)
        if posts.empty:
            continue
        all_rows.extend(posts.to_dict(orient="records"))
    if not all_rows:
        return pd.DataFrame()
    return pd.DataFrame(SyncBlueskyPostModel.model_validate(row).model_dump() for row in all_rows)


def generate_bluesky_features(
    dataset_id: str,
    *,
    batch_size: int = 64,
    max_concurrency: int = 80,
    opik_enabled: bool = False,
    feature_subset: list[str] | None = None,
) -> dict[str, Path]:
    """Load Bluesky posts and generate the requested feature labels."""
    dataset_id = validate_dataset_id(dataset_id)

    features_dir = dataset_root("bluesky", dataset_id) / StorageStage.FEATURES
    _retry_pending_upload(dataset_id, features_dir)

    preprocessed_storage = BlueskyStorageManager(StorageStage.PREPROCESSED, dataset_id)
    if preprocessed_storage.latest_run_dir() is None:
        raise FileNotFoundError(f"No preprocessed runs found for dataset {dataset_id}")
    require_all_runs_uploaded(preprocessed_storage, dataset_id)

    features_subset = generate_feature_subset(feature_subset)
    run_config = FeatureRunConfig(
        batch_size=batch_size,
        max_concurrency=max_concurrency,
        opik_enabled=opik_enabled,
    )
    posts = load_all_posts(dataset_id)
    config = bluesky_feature_config(
        dataset_id,
        run_config=run_config,
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
            for feature_name, path in written.items():
                _publish_feature(dataset_id, feature_name, path)
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
        feature_subset=features_from_cli(features),
    )


if __name__ == "__main__":
    typer.run(main)
