"""Generate features for preprocessed Twitter posts.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/generate_features/generate_twitter_features.py \\
        --dataset-id twitter_<uuid> --batch-size 64
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import typer
from pydantic import BaseModel

from data_platform.generate_features.generate_features import FeatureGenerationConfig
from data_platform.generate_features.models import FeatureRunConfig
from data_platform.generate_features.platform_cli import (
    features_from_cli,
    generate_feature_subset,
    run_feature_generation,
)
from data_platform.generate_features.registry import (
    FEATURE_REGISTRY,
    default_feature_registry,
)
from data_platform.models.sync import SyncTwitterPostModel
from data_platform.utils.dataset import dataset_root, validate_dataset_id
from data_platform.utils.feature_labels import FeatureLabelQuery
from data_platform.utils.platform_ids import TWITTER_BINDING
from data_platform.utils.storage import StorageManager, TwitterStorageManager

ID_COLUMN = TWITTER_BINDING.records_id_column
TEXT_COLUMN = TWITTER_BINDING.text_column
FEATURE_CSV_ID_COLUMN = TWITTER_BINDING.feature_csv_id_column


def twitter_feature_config(
    dataset_id: str,
    *,
    run_config: FeatureRunConfig,
    preprocessed_run: str | None = None,
    features_subset: tuple[str, ...] | None = None,
) -> FeatureGenerationConfig:
    """Build a FeatureGenerationConfig for Twitter flat feature CSV output."""
    dataset_id = validate_dataset_id(dataset_id)
    registry = (
        {name: FEATURE_REGISTRY[name] for name in features_subset}
        if features_subset
        else default_feature_registry()
    )

    binding = TWITTER_BINDING
    feature_label_storage = StorageManager(
        "twitter", "features", BaseModel, dataset_id, records_filename="features"
    )
    return FeatureGenerationConfig(
        platform="twitter",
        id_column=binding.records_id_column,
        text_column=binding.text_column,
        feature_registry=registry,
        input_storage=TwitterStorageManager("preprocessed", dataset_id),
        features_dir=feature_label_storage.root_dir,
        feature_label_query=FeatureLabelQuery(
            feature_storage=feature_label_storage,
            id_column=binding.records_id_column,
            feature_csv_id_column=binding.feature_csv_id_column,
        ),
        run_config=run_config,
        preprocessed_run=preprocessed_run,
    )


def load_posts(dataset_id: str, preprocessed_run: str | None = None) -> pd.DataFrame:
    """Load preprocessed posts from the latest or a pinned preprocessing run."""
    storage = TwitterStorageManager("preprocessed", dataset_id)
    if preprocessed_run:
        run_dir = dataset_root("twitter", dataset_id) / preprocessed_run
        posts = storage.load_records(run_dir)
    else:
        posts = storage.load_records(latest=True)
    if posts.empty:
        return posts.copy()

    return pd.DataFrame(
        SyncTwitterPostModel.model_validate(row).model_dump()
        for row in posts.to_dict(orient="records")
    )


def generate_twitter_features(
    dataset_id: str,
    *,
    batch_size: int = 64,
    max_concurrency: int = 80,
    opik_enabled: bool = False,
    preprocessed_run: str | None = None,
    feature_subset: list[str] | None = None,
) -> dict[str, Path]:
    """Load Twitter posts and generate the requested feature labels."""
    dataset_id = validate_dataset_id(dataset_id)
    features_subset = generate_feature_subset(feature_subset)

    run_config = FeatureRunConfig(
        batch_size=batch_size,
        max_concurrency=max_concurrency,
        opik_enabled=opik_enabled,
    )
    posts = load_posts(dataset_id, preprocessed_run)
    config = twitter_feature_config(
        dataset_id,
        run_config=run_config,
        preprocessed_run=preprocessed_run,
        features_subset=features_subset,
    )
    return run_feature_generation(
        posts,
        config,
        empty_message="generate_twitter_features: no preprocessed posts found",
    )


def main(
    dataset_id: str = typer.Option(
        ...,
        "--dataset-id",
        help="Dataset identifier from ingestion YAML (twitter_<uuid>)",
    ),
    batch_size: int = typer.Option(64, "--batch-size"),
    max_concurrency: int = typer.Option(80, "--max-concurrency"),
    opik_enabled: bool = typer.Option(False, "--opik", help="Enable Opik telemetry"),
    preprocessed_run: str | None = typer.Option(
        None,
        "--preprocessed-run",
        help="Pin preprocessed run path, e.g. preprocessed/2026_06_01-16:30:00",
    ),
    features: list[str] | None = typer.Option(
        None,
        "--features",
        help="Feature name(s); repeat the flag per feature, e.g. --features is_political",
    ),
) -> None:
    """CLI entrypoint for resumable Twitter feature generation."""
    generate_twitter_features(
        dataset_id,
        batch_size=batch_size,
        max_concurrency=max_concurrency,
        opik_enabled=opik_enabled,
        preprocessed_run=preprocessed_run,
        feature_subset=features_from_cli(features),
    )


if __name__ == "__main__":
    typer.run(main)
