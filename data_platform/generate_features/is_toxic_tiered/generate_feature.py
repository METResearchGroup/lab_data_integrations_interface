"""Perspective API feature: tiered toxicity labels from toxicity probability.

Toxicity tiers: low (<= 0.1), medium (0.1-0.7), high (>= 0.7).

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/generate_features/is_toxic_tiered/generate_feature.py
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ml_tooling.perspective_api import get_toxicity_prob

ToxicityTier = Literal["low", "medium", "high"]

LOW_MAX = 0.1
HIGH_MIN = 0.7


class IsToxicTieredModel(BaseModel):
    uri: str
    toxicity_prob: float = Field(description="Perspective API TOXICITY probability in [0, 1].")
    toxicity_tier: ToxicityTier = Field(
        description="Toxicity tiers: low (<= 0.1), medium (0.1-0.7), high (>= 0.7)."
    )


def toxicity_tier_from_prob(toxicity_prob: float) -> ToxicityTier:
    """Map a toxicity probability to low, medium, or high tier."""
    if toxicity_prob <= LOW_MAX:
        return "low"
    if toxicity_prob >= HIGH_MIN:
        return "high"
    return "medium"


def generate_feature(uri: str, text: str) -> IsToxicTieredModel:
    """Score text toxicity and return the tiered label."""
    toxicity_prob = get_toxicity_prob(text)
    return IsToxicTieredModel(
        uri=uri,
        toxicity_prob=toxicity_prob,
        toxicity_tier=toxicity_tier_from_prob(toxicity_prob),
    )


if __name__ == "__main__":
    samples = [
        ("at://example/post/1", "Thanks for the thoughtful discussion everyone."),
        ("at://example/post/2", "That take is pretty rude, but I see your point."),
        ("at://example/post/3", "You are worthless garbage and should disappear."),
    ]
    for uri, text in samples:
        print(generate_feature(uri, text).model_dump())
