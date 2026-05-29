"""Generate LLM features for preprocessed Bluesky posts.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/generate_features/generate_bluesky_features.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_platform.generate_features.generate_features import (
    FeatureGenerationConfig,
    generate_features,
)
from data_platform.generate_features.is_news_or_opinion.generate_feature import (
    IsNewsOrOpinionModel,
)
from data_platform.generate_features.registry import FEATURE_REGISTRY
from data_platform.models.sync import SyncBlueskyPostModel
from data_platform.utils.storage import BlueskyStorageManager, StorageManager

PREPROCESSED_STORAGE = BlueskyStorageManager("preprocessed")
FEATURES_RUN_STORAGE = StorageManager(
    "bluesky",
    "features",
    IsNewsOrOpinionModel,
    records_filename="_run.csv",
)

URI_COLUMN = "uri"
TEXT_COLUMN = "text"


def bluesky_feature_config() -> FeatureGenerationConfig:
    return FeatureGenerationConfig(
        platform="bluesky",
        id_column=URI_COLUMN,
        text_column=TEXT_COLUMN,
        feature_registry=FEATURE_REGISTRY,
        input_storage=PREPROCESSED_STORAGE,
        output_run_storage=FEATURES_RUN_STORAGE,
    )


def load_posts() -> pd.DataFrame:
    """Load preprocessed posts from the latest preprocessing run."""
    posts = PREPROCESSED_STORAGE.load_records(latest=True)
    if posts.empty:
        return posts.copy()

    return pd.DataFrame(
        SyncBlueskyPostModel.model_validate(row).model_dump()
        for row in posts.to_dict(orient="records")[:10] # TODO: remove once testing is done.
    )


def generate_bluesky_features() -> dict[str, Path]:
    """Load Bluesky posts and generate all configured features."""
    posts = load_posts()
    if posts.empty:
        print("generate_bluesky_features: no preprocessed posts found")
        return {}

    return generate_features(posts, bluesky_feature_config())


if __name__ == "__main__":
    generate_bluesky_features()
