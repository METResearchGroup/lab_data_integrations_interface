from __future__ import annotations

import pytest

from data_platform.generate_features.generate_reddit_features import reddit_feature_config
from data_platform.generate_features.is_toxic_tiered_v2.generate_feature import (
    IsToxicTieredV2Model,
    generate_feature,
    toxicity_tier_from_probs,
)
from data_platform.generate_features.models import FeatureRunConfig
from data_platform.generate_features.platform_cli import generate_feature_subset
from data_platform.generate_features.registry import (
    FEATURE_REGISTRY,
    default_feature_registry,
)


@pytest.mark.parametrize(
    ("toxicity_prob", "severe_toxicity_prob", "expected"),
    [
        (0.3, 0.9, "low"),
        (0.6, 0.3, "medium"),
        (0.6, 0.8, "high"),
        (0.5, 0.9, "low"),
        (0.51, 0.5, "medium"),
    ],
)
def test_toxicity_tier_from_probs(
    toxicity_prob: float,
    severe_toxicity_prob: float,
    expected: str,
) -> None:
    assert toxicity_tier_from_probs(toxicity_prob, severe_toxicity_prob) == expected


def test_feature_registry_includes_is_toxic_tiered_v2() -> None:
    assert "is_toxic_tiered_v2" in FEATURE_REGISTRY


def test_default_feature_registry_excludes_opt_in_features() -> None:
    default_registry = default_feature_registry()
    assert "is_toxic_tiered_v2" not in default_registry
    assert "is_toxic_tiered" in default_registry


def test_reddit_feature_config_default_registry_excludes_v2() -> None:
    config = reddit_feature_config(
        "reddit_f47ac10b-58cc-4372-a567-0e02b2c3d479",
        run_config=FeatureRunConfig(),
    )
    assert "is_toxic_tiered_v2" not in config.feature_registry


def test_generate_feature_subset_includes_v2() -> None:
    assert generate_feature_subset(["is_toxic_tiered_v2"]) == ("is_toxic_tiered_v2",)


def test_generate_feature_returns_expected_schema(monkeypatch) -> None:
    monkeypatch.setattr(
        "data_platform.generate_features.is_toxic_tiered_v2.generate_feature.get_toxicity_probs",
        lambda text: (0.6, 0.8),
    )
    monkeypatch.setattr(
        "data_platform.generate_features.is_toxic_tiered_v2.generate_feature.get_current_timestamp",
        lambda: "2026-06-12T00:00:00Z",
    )

    result = generate_feature("at://example/post/1", "some text")

    assert isinstance(result, IsToxicTieredV2Model)
    assert result.uri == "at://example/post/1"
    assert result.label_timestamp == "2026-06-12T00:00:00Z"
    assert result.toxicity_prob == 0.6
    assert result.severe_toxicity_prob == 0.8
    assert result.toxicity_tier == "high"
