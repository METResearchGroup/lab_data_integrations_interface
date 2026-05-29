"""Generate LLM features for preprocessed Bluesky posts.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/generate_features/generate_bluesky_features.py
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel
from tqdm import tqdm

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
from lib.timestamp_utils import get_current_timestamp

PREPROCESSED_STORAGE = BlueskyStorageManager("preprocessed")
FEATURES_RUN_STORAGE = StorageManager(
    "bluesky",
    "features",
    IsNewsOrOpinionModel,
    records_filename="_run.csv",
)

URI_COLUMN = "uri"
TEXT_COLUMN = "text"

FeatureFn = Callable[[str, str], BaseModel]


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    generate_fn: FeatureFn
    model: type[BaseModel]


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


def load_posts() -> pd.DataFrame:
    """Load preprocessed posts from the latest preprocessing run."""
    posts = PREPROCESSED_STORAGE.load_records(latest=True)
    if posts.empty:
        return posts.copy()

    return pd.DataFrame(
        SyncBlueskyPostModel.model_validate(row).model_dump()
        for row in posts.to_dict(orient="records")
    )


def filter_posts_needing_features(
    posts: pd.DataFrame,
    feature_name: str,
) -> pd.DataFrame:
    """Return posts that still need labels for feature_name.

    Stub: passthrough all posts. Later this will diff against existing
    feature labels (likely by uri).
    """
    _ = feature_name
    return posts.copy()


def run_feature_pipeline(
    posts: pd.DataFrame,
    generate_fn: FeatureFn,
    *,
    feature_name: str,
) -> list[dict[str, Any]]:
    """Generate feature labels for each post."""
    if posts.empty:
        return []

    rows: list[dict[str, Any]] = []
    for _, post in tqdm(
        posts.iterrows(),
        total=len(posts),
        desc=feature_name,
    ):
        result = generate_fn(str(post[URI_COLUMN]), str(post[TEXT_COLUMN]))
        rows.append(result.model_dump())
    return rows


def save_feature_labels(
    feature_name: str,
    rows: list[dict[str, Any]],
    model: type[BaseModel],
    run_dir: Path,
) -> Path:
    """Persist feature labels for one feature to the shared features run directory."""
    storage = StorageManager(
        "bluesky",
        "features",
        model,
        records_filename=f"{feature_name}.csv",
    )
    return storage.write_records(rows, run_dir, filename=f"{feature_name}.csv")


def generate_and_export_feature_labels(
    posts: pd.DataFrame,
    spec: FeatureSpec,
    output_run_dir: Path,
) -> tuple[Path, int]:
    """Generate labels for one feature and write them to the run directory."""
    candidates = filter_posts_needing_features(posts, spec.name)
    labels = run_feature_pipeline(
        candidates,
        spec.generate_fn,
        feature_name=spec.name,
    )
    csv_path = save_feature_labels(spec.name, labels, spec.model, output_run_dir)
    print(
        f"generate_features: {spec.name} -> "
        f"{len(labels)} labels from {len(candidates)} candidate posts"
    )
    return csv_path, len(labels)


def generate_features() -> dict[str, Path]:
    """Load preprocessed posts, generate all features, and write label CSVs."""
    posts = load_posts()
    if posts.empty:
        print("generate_features: no preprocessed posts found")
        return {}

    source_run_dir = PREPROCESSED_STORAGE.latest_run_dir()
    output_run_dir = FEATURES_RUN_STORAGE.create_new_run_dir(get_current_timestamp())

    written: dict[str, Path] = {}
    counts: dict[str, int] = {}

    for feature_name, spec in FEATURE_REGISTRY.items():
        csv_path, label_count = generate_and_export_feature_labels(
            posts,
            spec,
            output_run_dir,
        )
        written[feature_name] = csv_path
        counts[feature_name] = label_count

    FEATURES_RUN_STORAGE.write_run_metadata(
        output_run_dir,
        {
            "source_preprocessed_run": str(source_run_dir),
            "feature_counts": counts,
            "features": list(FEATURE_REGISTRY.keys()),
        },
    )

    print(f"generate_features: wrote {len(written)} feature files to {output_run_dir}")
    return written


if __name__ == "__main__":
    generate_features()
