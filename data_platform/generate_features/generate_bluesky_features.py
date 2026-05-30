"""Generate features for preprocessed Bluesky posts.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/generate_features/generate_bluesky_features.py --dataset-id bluesky_<uuid>
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import typer

from data_platform.generate_features.generate_features import (
    FeatureGenerationConfig,
    generate_features,
)
from data_platform.generate_features.is_news_or_opinion.generate_feature import (
    IsNewsOrOpinionModel,
)
from data_platform.generate_features.registry import FEATURE_REGISTRY
from data_platform.models.sync import SyncBlueskyPostModel
from data_platform.utils.dataset import dataset_root, validate_dataset_id
from data_platform.utils.feature_labels import FeatureLabelQuery
from data_platform.utils.storage import BlueskyStorageManager, StorageManager

URI_COLUMN = "uri"
TEXT_COLUMN = "text"


def bluesky_feature_config(dataset_id: str) -> FeatureGenerationConfig:
    dataset_id = validate_dataset_id(dataset_id)
    preprocessed_storage = BlueskyStorageManager("preprocessed", dataset_id)
    features_root = dataset_root("bluesky", dataset_id) / "features"
    features_run_storage = StorageManager(
        "bluesky",
        "features",
        IsNewsOrOpinionModel,
        dataset_id,
        records_filename="_run.csv",
    )
    return FeatureGenerationConfig(
        platform="bluesky",
        id_column=URI_COLUMN,
        text_column=TEXT_COLUMN,
        feature_registry=FEATURE_REGISTRY,
        input_storage=preprocessed_storage,
        output_run_storage=features_run_storage,
        feature_label_query=FeatureLabelQuery(
            features_root=features_root,
            id_column=URI_COLUMN,
        ),
    )


def load_posts(dataset_id: str) -> pd.DataFrame:
    """Load preprocessed posts from the latest preprocessing run."""
    posts = BlueskyStorageManager("preprocessed", dataset_id).load_records(latest=True)
    if posts.empty:
        return posts.copy()

    return pd.DataFrame(
        SyncBlueskyPostModel.model_validate(row).model_dump()
        for row in posts.to_dict(orient="records")
    )


def generate_bluesky_features(dataset_id: str) -> dict[str, Path]:
    """Load Bluesky posts and generate all configured features."""
    dataset_id = validate_dataset_id(dataset_id)
    posts = load_posts(dataset_id)
    if posts.empty:
        print("generate_bluesky_features: no preprocessed posts found")
        return {}

    return generate_features(posts, bluesky_feature_config(dataset_id))


def main(
    dataset_id: str = typer.Option(
        ...,
        "--dataset-id",
        help="Dataset identifier from ingestion YAML (bluesky_<uuid>)",
    ),
) -> None:
    generate_bluesky_features(dataset_id)


if __name__ == "__main__":
    typer.run(main)
