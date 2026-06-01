from __future__ import annotations

import pytest

from data_platform.generate_features.platform_cli import (
    features_from_cli,
    generate_feature_subset,
)


def test_generate_feature_subset_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown features"):
        generate_feature_subset(["not_a_real_feature"])


def test_generate_feature_subset_none_returns_none() -> None:
    assert generate_feature_subset(None) is None
    assert generate_feature_subset([]) is None


def test_generate_feature_subset_valid_names() -> None:
    assert generate_feature_subset(["is_political"]) == ("is_political",)


def test_features_from_cli_none() -> None:
    assert features_from_cli(None) is None


def test_features_from_cli_comma_and_repeat() -> None:
    assert features_from_cli(["is_political", "is_news_or_opinion,is_self_contained"]) == [
        "is_political",
        "is_news_or_opinion",
        "is_self_contained",
    ]


def test_features_from_cli_empty_strings_returns_none() -> None:
    assert features_from_cli([""]) is None
