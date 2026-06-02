from __future__ import annotations

from data_platform.generate_features.is_likely_spam.generate_feature import (
    IsLikelySpamModel,
    generate_feature,
)
from data_platform.generate_features.registry import FEATURE_REGISTRY


def test_feature_registry_includes_is_likely_spam() -> None:
    assert "is_likely_spam" in FEATURE_REGISTRY


def test_generate_feature_returns_expected_schema(monkeypatch) -> None:
    class _Result:
        is_likely_spam = True

    def fake_structured_chat_completion(**kwargs):
        return _Result()

    monkeypatch.setattr(
        "data_platform.generate_features.is_likely_spam.generate_feature.structured_chat_completion",
        fake_structured_chat_completion,
    )
    monkeypatch.setattr(
        "data_platform.generate_features.is_likely_spam.generate_feature.get_current_timestamp",
        lambda: "2026-06-02T00:00:00Z",
    )

    result = generate_feature("at://example/post/1", "click this link")

    assert isinstance(result, IsLikelySpamModel)
    assert result.uri == "at://example/post/1"
    assert result.label_timestamp == "2026-06-02T00:00:00Z"
    assert result.is_likely_spam is True
