from __future__ import annotations

from pathlib import Path

import typer

from experiments.reddit_data_dump_labeling_2026_06_16.patch_data_root import patch_data_root

patch_data_root()

from data_platform.generate_features.generate_reddit_features import (
    load_comments,
    reddit_feature_config,
)
from data_platform.generate_features.platform_cli import (
    features_from_cli,
    generate_feature_subset,
    run_feature_generation,
)
from experiments.reddit_data_dump_labeling_2026_06_16.paths import dataset_id_for
from data_platform.generate_features.models import FeatureRunConfig

LLM_FEATURES = (
    "is_news_or_opinion",
    "is_political",
    "is_likely_spam",
    "is_self_contained",
    "is_structurally_complete",
    "political_stance",
)


def run_features(
    batch: str,
    *,
    features: list[str] | None = None,
    batch_size: int = 64,
    max_concurrency: int = 80,
    opik_enabled: bool = False,
    preprocessed_run: str | None = None,
    limit: int | None = None,
    data_root: Path | None = None,
) -> dict[str, Path]:
    if data_root is not None:
        patch_data_root(data_root)

    dataset_id = dataset_id_for(batch)
    requested = features_from_cli(features)
    if requested is None:
        features_subset = LLM_FEATURES
    else:
        unknown = set(requested) - set(LLM_FEATURES)
        if unknown:
            raise ValueError(
                f"Unsupported features for this experiment: {sorted(unknown)}; "
                f"allowed: {list(LLM_FEATURES)}"
            )
        features_subset = generate_feature_subset(requested)

    run_config = FeatureRunConfig(
        batch_size=batch_size,
        max_concurrency=max_concurrency,
        opik_enabled=opik_enabled,
    )
    comments = load_comments(dataset_id, preprocessed_run)
    if limit is not None:
        comments = comments.head(limit)

    config = reddit_feature_config(
        dataset_id,
        run_config=run_config,
        preprocessed_run=preprocessed_run,
        features_subset=features_subset,
    )
    return run_feature_generation(
        comments,
        config,
        empty_message="run_features: no preprocessed comments found",
    )


def main(
    batch: str = typer.Option(..., "--batch", help="Batch key from batches.yaml"),
    features: list[str] | None = typer.Option(
        None,
        "--features",
        help="Feature name(s); repeat the flag per feature",
    ),
    batch_size: int = typer.Option(64, "--batch-size"),
    max_concurrency: int = typer.Option(80, "--max-concurrency"),
    opik_enabled: bool = typer.Option(False, "--opik", help="Enable Opik telemetry"),
    preprocessed_run: str | None = typer.Option(
        None,
        "--preprocessed-run",
        help="Pin preprocessed run path, e.g. preprocessed/2026_05_29-20:14:22",
    ),
    limit: int | None = typer.Option(None, "--limit", help="Optional row cap for pilot runs"),
) -> None:
    written = run_features(
        batch,
        features=features,
        batch_size=batch_size,
        max_concurrency=max_concurrency,
        opik_enabled=opik_enabled,
        preprocessed_run=preprocessed_run,
        limit=limit,
    )
    for feature_name, path in written.items():
        print(f"run_features: {feature_name} -> {path}")


if __name__ == "__main__":
    typer.run(main)
