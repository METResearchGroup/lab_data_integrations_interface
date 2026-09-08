"""Load optional per-dataset feature config and apply registry overrides."""

from __future__ import annotations

from typing import Any

import yaml

from data_platform.generate_features.is_toxic_tiered.generate_feature import (
    HIGH_MIN,
    LOW_MAX,
    make_generate_feature,
)
from data_platform.generate_features.models import FeatureSpec
from data_platform.utils.dataset import dataset_root


def load_dataset_feature_config(platform: str, dataset_id: str) -> dict[str, Any]:
    """Load optional features/config.yaml for a dataset; return {} if missing."""
    path = dataset_root(platform, dataset_id) / "features" / "config.yaml"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"features/config.yaml must be a mapping: {path}")
    return data


def _validate_toxic_tiered_thresholds(low_max: float, high_min: float) -> None:
    if low_max >= high_min:
        raise ValueError(f"is_toxic_tiered requires low_max < high_min, got {low_max} >= {high_min}")


def apply_toxic_tiered_overrides(
    registry: dict[str, FeatureSpec],
    feature_config: dict[str, Any],
) -> dict[str, FeatureSpec]:
    """Return a registry copy with is_toxic_tiered thresholds overridden when configured."""
    spec = registry.get("is_toxic_tiered")
    if spec is None:
        return registry

    tiered_config = feature_config.get("is_toxic_tiered")
    if not tiered_config:
        return registry

    low_max = float(tiered_config.get("low_max", LOW_MAX))
    high_min = float(tiered_config.get("high_min", HIGH_MIN))
    _validate_toxic_tiered_thresholds(low_max, high_min)

    updated_spec = FeatureSpec(
        name=spec.name,
        model=spec.model,
        engine_type=spec.engine_type,
        generate_fn=make_generate_feature(low_max=low_max, high_min=high_min),
    )
    return {**registry, "is_toxic_tiered": updated_spec}
