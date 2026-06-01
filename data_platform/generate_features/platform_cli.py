"""Shared CLI helpers and orchestration for platform feature generation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_platform.generate_features.generate_features import (
    FeatureGenerationConfig,
    generate_features,
)
from data_platform.generate_features.registry import FEATURE_REGISTRY


def generate_feature_subset(features: list[str] | None) -> tuple[str, ...] | None:
    """Validate feature names and return a registry subset, or None to run all features."""
    if not features:
        return None
    unknown = set(features) - set(FEATURE_REGISTRY)
    if unknown:
        raise ValueError(f"Unknown features: {sorted(unknown)}")
    return tuple(features)


def features_from_cli(raw: list[str] | None) -> list[str] | None:
    """Normalize Typer --features values into a list of feature names."""
    if raw is None:
        return None
    names = [part.strip() for item in raw for part in item.split(",") if part.strip()]
    return names or None


def run_feature_generation(
    records: pd.DataFrame,
    config: FeatureGenerationConfig,
    *,
    empty_message: str,
) -> dict[str, Path]:
    if records.empty:
        print(empty_message)
        return {}
    return generate_features(records, config)
