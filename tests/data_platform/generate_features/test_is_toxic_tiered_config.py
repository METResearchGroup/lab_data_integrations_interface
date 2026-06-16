from __future__ import annotations

import pytest

from data_platform.generate_features.dataset_feature_config import (
    apply_toxic_tiered_overrides,
    load_dataset_feature_config,
)
from data_platform.generate_features.is_toxic_tiered.generate_feature import (
    HIGH_MIN,
    LOW_MAX,
    make_generate_feature,
    toxicity_tier_from_prob,
)
from data_platform.generate_features.models import FeatureSpec
from data_platform.generate_features.registry import FEATURE_REGISTRY
from tests.data_platform.constants import VALID_REDDIT_DATASET_ID


def test_toxicity_tier_from_prob_uses_custom_thresholds() -> None:
    assert toxicity_tier_from_prob(0.25, low_max=0.3, high_min=0.5) == "low"
    assert toxicity_tier_from_prob(0.4, low_max=0.3, high_min=0.5) == "medium"
    assert toxicity_tier_from_prob(0.6, low_max=0.3, high_min=0.5) == "high"


def test_toxicity_tier_from_prob_defaults_match_module_constants() -> None:
    assert toxicity_tier_from_prob(0.05) == "low"
    assert toxicity_tier_from_prob(0.5) == "medium"
    assert toxicity_tier_from_prob(0.9) == "high"


def test_make_generate_feature_uses_custom_thresholds(monkeypatch) -> None:
    monkeypatch.setattr(
        "data_platform.generate_features.is_toxic_tiered.generate_feature.get_toxicity_prob",
        lambda _text: 0.25,
    )
    monkeypatch.setattr(
        "data_platform.generate_features.is_toxic_tiered.generate_feature.get_current_timestamp",
        lambda: "2026-06-15T00:00:00Z",
    )

    result = make_generate_feature(low_max=0.3, high_min=0.5)("at://example/1", "text")
    assert result.toxicity_prob == 0.25
    assert result.toxicity_tier == "low"


def test_load_dataset_feature_config_missing_file_returns_empty(data_root) -> None:
    assert load_dataset_feature_config("reddit", VALID_REDDIT_DATASET_ID) == {}


def test_load_dataset_feature_config_parses_valid_file(data_root) -> None:
    config_dir = data_root / "reddit" / VALID_REDDIT_DATASET_ID / "features"
    config_dir.mkdir(parents=True)
    (config_dir / "config.yaml").write_text(
        "is_toxic_tiered:\n  low_max: 0.3\n  high_min: 0.5\n",
        encoding="utf-8",
    )

    assert load_dataset_feature_config("reddit", VALID_REDDIT_DATASET_ID) == {
        "is_toxic_tiered": {"low_max": 0.3, "high_min": 0.5},
    }


def test_apply_toxic_tiered_overrides_rejects_invalid_thresholds() -> None:
    registry = {"is_toxic_tiered": FEATURE_REGISTRY["is_toxic_tiered"]}
    with pytest.raises(ValueError, match="low_max < high_min"):
        apply_toxic_tiered_overrides(
            registry,
            {"is_toxic_tiered": {"low_max": 0.5, "high_min": 0.3}},
        )


def test_apply_toxic_tiered_overrides_builds_custom_generate_fn(monkeypatch) -> None:
    monkeypatch.setattr(
        "data_platform.generate_features.is_toxic_tiered.generate_feature.get_toxicity_prob",
        lambda _text: 0.25,
    )
    monkeypatch.setattr(
        "data_platform.generate_features.is_toxic_tiered.generate_feature.get_current_timestamp",
        lambda: "2026-06-15T00:00:00Z",
    )

    registry = apply_toxic_tiered_overrides(
        {"is_toxic_tiered": FEATURE_REGISTRY["is_toxic_tiered"]},
        {"is_toxic_tiered": {"low_max": 0.3, "high_min": 0.5}},
    )
    result = registry["is_toxic_tiered"].generate_fn("at://example/1", "text")
    assert result.toxicity_tier == "low"


def test_module_defaults_unchanged() -> None:
    assert LOW_MAX == 0.1
    assert HIGH_MIN == 0.7
