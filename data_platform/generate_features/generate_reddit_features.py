"""Generate features for preprocessed Reddit comments.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/generate_features/generate_reddit_features.py \\
        --dataset-id reddit_<uuid> --batch-size 64
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
from data_platform.generate_features.registry import FEATURE_REGISTRY
from data_platform.models.sync import SyncRedditCommentModel
from data_platform.utils.dataset import validate_dataset_id
from data_platform.utils.feature_labels import FeatureLabelQuery
from data_platform.utils.platform_ids import REDDIT_BINDING
from data_platform.utils.storage import RedditStorageManager, StorageManager, StorageStage

ID_COLUMN = REDDIT_BINDING.records_id_column
TEXT_COLUMN = REDDIT_BINDING.text_column
FEATURE_FILE_ID_COLUMN = REDDIT_BINDING.feature_file_id_column


def reddit_feature_config(
    dataset_id: str,
    *,
    run_config: FeatureRunConfig,
    features_subset: tuple[str, ...] | None = None,
) -> FeatureGenerationConfig:
    """Build a FeatureGenerationConfig for Reddit flat feature CSV output."""
    dataset_id = validate_dataset_id(dataset_id)
    registry = FEATURE_REGISTRY
    if features_subset:
        registry = {name: FEATURE_REGISTRY[name] for name in features_subset}

    binding = REDDIT_BINDING
    feature_label_storage = StorageManager(
        "reddit",
        StorageStage.FEATURES,
        BaseModel,
        dataset_id,
        records_filename="features",
    )
    return FeatureGenerationConfig(
        platform="reddit",
        id_column=binding.records_id_column,
        text_column=binding.text_column,
        feature_registry=registry,
        input_storage=RedditStorageManager(StorageStage.PREPROCESSED, dataset_id),
        features_dir=feature_label_storage.root_dir,
        feature_label_query=FeatureLabelQuery(
            feature_storage=feature_label_storage,
            id_column=binding.records_id_column,
            feature_file_id_column=binding.feature_file_id_column,
        ),
        run_config=run_config,
    )


def load_comments(dataset_id: str) -> pd.DataFrame:
    """Load preprocessed comments from all preprocessed run dirs."""
    storage = RedditStorageManager(StorageStage.PREPROCESSED, dataset_id)
    if not storage.root_dir.exists():
        return pd.DataFrame()
    all_rows = []
    for run_dir in sorted(storage.root_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        comments = storage.load_records(run_dir=run_dir)
        if comments.empty:
            continue
        all_rows.extend(comments.to_dict(orient="records"))
    if not all_rows:
        return pd.DataFrame()
    return pd.DataFrame(SyncRedditCommentModel.model_validate(row).model_dump() for row in all_rows)


def generate_reddit_features(
    dataset_id: str,
    *,
    batch_size: int = 64,
    max_concurrency: int = 80,
    opik_enabled: bool = False,
    feature_subset: list[str] | None = None,
) -> dict[str, Path]:
    """Load Reddit comments and generate the requested feature labels."""
    dataset_id = validate_dataset_id(dataset_id)
    features_subset = generate_feature_subset(feature_subset)

    run_config = FeatureRunConfig(
        batch_size=batch_size,
        max_concurrency=max_concurrency,
        opik_enabled=opik_enabled,
    )
    comments = load_comments(dataset_id)
    config = reddit_feature_config(
        dataset_id,
        run_config=run_config,
        features_subset=features_subset,
    )
    return run_feature_generation(
        comments,
        config,
        empty_message="generate_reddit_features: no preprocessed comments found",
    )


def main(
    dataset_id: str = typer.Option(
        ...,
        "--dataset-id",
        help="Dataset identifier from ingestion YAML (reddit_<uuid>)",
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
    """CLI entrypoint for resumable Reddit feature generation."""
    generate_reddit_features(
        dataset_id,
        batch_size=batch_size,
        max_concurrency=max_concurrency,
        opik_enabled=opik_enabled,
        feature_subset=features_from_cli(features),
    )


if __name__ == "__main__":
    typer.run(main)
