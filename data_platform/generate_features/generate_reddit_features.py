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

from data_platform.generate_features.dataset_feature_config import (
    apply_toxic_tiered_overrides,
    load_dataset_feature_config,
)
from data_platform.generate_features.generate_features import FeatureGenerationConfig
from data_platform.generate_features.models import FeatureRunConfig
from data_platform.generate_features.platform_cli import (
    features_from_cli,
    generate_feature_subset,
    run_feature_generation,
)
from data_platform.generate_features.registry import FEATURE_REGISTRY
from data_platform.models.sync import SyncRedditCommentModel
from data_platform.utils.dataset import dataset_root, validate_dataset_id
from data_platform.utils.feature_labels import FeatureLabelQuery
from data_platform.utils.platform_ids import REDDIT_BINDING
from data_platform.utils.storage import RedditStorageManager, StorageManager

ID_COLUMN = REDDIT_BINDING.records_id_column
TEXT_COLUMN = REDDIT_BINDING.text_column
FEATURE_CSV_ID_COLUMN = REDDIT_BINDING.feature_csv_id_column


def reddit_feature_config(
    dataset_id: str,
    *,
    run_config: FeatureRunConfig,
    preprocessed_run: str | None = None,
    features_subset: tuple[str, ...] | None = None,
) -> FeatureGenerationConfig:
    """Build a FeatureGenerationConfig for Reddit flat feature CSV output."""
    dataset_id = validate_dataset_id(dataset_id)
    registry = FEATURE_REGISTRY
    if features_subset:
        registry = {name: FEATURE_REGISTRY[name] for name in features_subset}
    feature_config = load_dataset_feature_config("reddit", dataset_id)
    registry = apply_toxic_tiered_overrides(registry, feature_config)

    binding = REDDIT_BINDING
    feature_label_storage = StorageManager(
        "reddit", "features", BaseModel, dataset_id, records_filename="features"
    )
    return FeatureGenerationConfig(
        platform="reddit",
        id_column=binding.records_id_column,
        text_column=binding.text_column,
        feature_registry=registry,
        input_storage=RedditStorageManager("preprocessed", dataset_id),
        features_dir=feature_label_storage.root_dir,
        feature_label_query=FeatureLabelQuery(
            feature_storage=feature_label_storage,
            id_column=binding.records_id_column,
            feature_csv_id_column=binding.feature_csv_id_column,
        ),
        run_config=run_config,
        preprocessed_run=preprocessed_run,
    )


def load_comments(dataset_id: str, preprocessed_run: str | None = None) -> pd.DataFrame:
    """Load preprocessed comments from the latest or a pinned preprocessing run."""
    storage = RedditStorageManager("preprocessed", dataset_id)
    if preprocessed_run:
        run_dir = dataset_root("reddit", dataset_id) / preprocessed_run
        comments = storage.load_records(run_dir)
    else:
        comments = storage.load_records(latest=True)
    if comments.empty:
        return comments.copy()

    # NOTE to future users: for the MirrorView study, we limited it to the
    # first 15,000 comments.
    # comments = comments.head(15000)

    return pd.DataFrame(
        SyncRedditCommentModel.model_validate(row).model_dump()
        for row in comments.to_dict(orient="records")
    )


def generate_reddit_features(
    dataset_id: str,
    *,
    batch_size: int = 64,
    max_concurrency: int = 80,
    opik_enabled: bool = False,
    preprocessed_run: str | None = None,
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
    comments = load_comments(dataset_id, preprocessed_run)
    config = reddit_feature_config(
        dataset_id,
        run_config=run_config,
        preprocessed_run=preprocessed_run,
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
    """CLI entrypoint for resumable Reddit feature generation."""
    generate_reddit_features(
        dataset_id,
        batch_size=batch_size,
        max_concurrency=max_concurrency,
        opik_enabled=opik_enabled,
        preprocessed_run=preprocessed_run,
        feature_subset=features_from_cli(features),
    )


if __name__ == "__main__":
    typer.run(main)
