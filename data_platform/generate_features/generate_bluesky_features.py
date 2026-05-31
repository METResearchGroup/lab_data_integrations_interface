"""Generate features for preprocessed Bluesky posts.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/generate_features/generate_bluesky_features.py \\
        --dataset-id bluesky_<uuid> --batch-size 64 --no-opik
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import typer

from data_platform.generate_features.generate_features import (
    FeatureGenerationConfig,
    generate_features,
)
from data_platform.generate_features.models import FeatureRunConfig
from data_platform.generate_features.registry import FEATURE_REGISTRY
from data_platform.models.sync import SyncBlueskyPostModel
from data_platform.utils.dataset import dataset_root, validate_dataset_id
from data_platform.utils.feature_labels import FeatureLabelQuery
from data_platform.utils.storage import BlueskyStorageManager

URI_COLUMN = "uri"
TEXT_COLUMN = "text"


def generate_feature_subset(features: list[str] | None) -> tuple[str, ...] | None:
    """Validate feature names and return a registry subset, or None to run all features."""
    if not features:
        return None
    unknown = set(features) - set(FEATURE_REGISTRY)
    if unknown:
        raise ValueError(f"Unknown features: {sorted(unknown)}")
    return tuple(features)


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

    features_dir = dataset_root("bluesky", dataset_id) / "features"
    return FeatureGenerationConfig(
        platform="bluesky",
        id_column=URI_COLUMN,
        text_column=TEXT_COLUMN,
        feature_registry=registry,
        input_storage=BlueskyStorageManager("preprocessed", dataset_id),
        features_dir=features_dir,
        feature_label_query=FeatureLabelQuery(
            features_root=features_dir,
            id_column=URI_COLUMN,
        ),
        run_config=run_config,
        preprocessed_run=preprocessed_run,
    )


def load_posts(dataset_id: str, preprocessed_run: str | None = None) -> pd.DataFrame:
    """Load preprocessed posts from the latest or a pinned preprocessing run."""
    storage = BlueskyStorageManager("preprocessed", dataset_id)
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
    max_concurrency: int = 20,
    no_opik: bool = False,
    preprocessed_run: str | None = None,
    feature_subset: list[str] | None = None,
) -> dict[str, Path]:
    """Load Bluesky posts and generate the requested feature labels."""
    dataset_id = validate_dataset_id(dataset_id)
    features_subset = generate_feature_subset(feature_subset)

    run_config = FeatureRunConfig(
        batch_size=batch_size,
        max_concurrency=max_concurrency,
        opik_enabled=not no_opik,
    )
    posts = load_posts(dataset_id, preprocessed_run)
    if posts.empty:
        print("generate_bluesky_features: no preprocessed posts found")
        return {}

    config = bluesky_feature_config(
        dataset_id,
        run_config=run_config,
        preprocessed_run=preprocessed_run,
        features_subset=features_subset,
    )
    return generate_features(posts, config)


def _features_from_cli(raw: list[str] | None) -> list[str] | None:
    """Normalize Typer --features values into a list of feature names."""
    if raw is None:
        return None
    names = [part.strip() for item in raw for part in item.split(",") if part.strip()]
    return names or None


def main(
    dataset_id: str = typer.Option(
        ...,
        "--dataset-id",
        help="Dataset identifier from ingestion YAML (bluesky_<uuid>)",
    ),
    batch_size: int = typer.Option(64, "--batch-size"),
    max_concurrency: int = typer.Option(20, "--max-concurrency"),
    no_opik: bool = typer.Option(False, "--no-opik"),
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
        no_opik=no_opik,
        preprocessed_run=preprocessed_run,
        feature_subset=_features_from_cli(features),
    )


if __name__ == "__main__":
    typer.run(main)
