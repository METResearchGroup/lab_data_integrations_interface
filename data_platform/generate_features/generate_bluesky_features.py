"""Generate LLM features for preprocessed Bluesky posts.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/generate_features/generate_bluesky_features.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_platform.generate_features.generate_features import (
    FeatureGenerationConfig,
    FeatureSpec,
    generate_features,
)
from data_platform.generate_features.is_news_or_opinion.generate_feature import (
    IsNewsOrOpinionModel,
    generate_feature as generate_is_news_or_opinion,
)
from data_platform.generate_features.is_political.generate_feature import (
    IsPoliticalModel,
    generate_feature as generate_is_political,
)
from data_platform.generate_features.is_self_contained.generate_feature import (
    IsSelfContainedModel,
    generate_feature as generate_is_self_contained,
)
from data_platform.generate_features.is_structurally_complete.generate_feature import (
    IsStructurallyCompleteModel,
    generate_feature as generate_is_structurally_complete,
)
from data_platform.generate_features.political_stance.generate_feature import (
    PoliticalStanceModel,
    generate_feature as generate_political_stance,
)
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

FEATURE_REGISTRY: dict[str, FeatureSpec] = {
    "is_news_or_opinion": FeatureSpec(
        name="is_news_or_opinion",
        generate_fn=generate_is_news_or_opinion,
        model=IsNewsOrOpinionModel,
    ),
    "is_political": FeatureSpec(
        name="is_political",
        generate_fn=generate_is_political,
        model=IsPoliticalModel,
    ),
    "is_self_contained": FeatureSpec(
        name="is_self_contained",
        generate_fn=generate_is_self_contained,
        model=IsSelfContainedModel,
    ),
    "is_structurally_complete": FeatureSpec(
        name="is_structurally_complete",
        generate_fn=generate_is_structurally_complete,
        model=IsStructurallyCompleteModel,
    ),
    "political_stance": FeatureSpec(
        name="political_stance",
        generate_fn=generate_political_stance,
        model=PoliticalStanceModel,
    ),
}


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
        for row in posts.to_dict(orient="records")
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
