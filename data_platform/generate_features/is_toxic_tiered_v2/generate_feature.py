"""Perspective API feature: tiered toxicity labels from TOXICITY + SEVERE_TOXICITY.

Tier logic: low if toxicity <= 0.5; high if toxicity > 0.5 and severe > 0.5; else medium.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/generate_features/is_toxic_tiered_v2/generate_feature.py
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from lib.timestamp_utils import get_current_timestamp
from ml_tooling.perspective_api import get_toxicity_probs

ToxicityTier = Literal["low", "medium", "high"]

LOW_MAX = 0.5
SEVERE_HIGH_MIN = 0.5


class IsToxicTieredV2Model(BaseModel):
    uri: str
    label_timestamp: str
    toxicity_prob: float = Field(description="Perspective API TOXICITY probability in [0, 1].")
    severe_toxicity_prob: float = Field(
        description="Perspective API SEVERE_TOXICITY probability in [0, 1]."
    )
    toxicity_tier: ToxicityTier = Field(
        description=(
            "Toxicity tiers: low (toxicity <= 0.5); high (toxicity > 0.5 and severe > 0.5); "
            "else medium."
        )
    )


def toxicity_tier_from_probs(toxicity_prob: float, severe_toxicity_prob: float) -> ToxicityTier:
    """Map TOXICITY and SEVERE_TOXICITY probabilities to low, medium, or high tier."""
    if toxicity_prob <= LOW_MAX:
        return "low"
    if severe_toxicity_prob > SEVERE_HIGH_MIN:
        return "high"
    return "medium"


def generate_feature(uri: str, text: str) -> IsToxicTieredV2Model:
    """Score text toxicity and return the tiered label with both probability signals."""
    toxicity_prob, severe_toxicity_prob = get_toxicity_probs(text)
    return IsToxicTieredV2Model(
        uri=uri,
        label_timestamp=get_current_timestamp(),
        toxicity_prob=toxicity_prob,
        severe_toxicity_prob=severe_toxicity_prob,
        toxicity_tier=toxicity_tier_from_probs(toxicity_prob, severe_toxicity_prob),
    )


if __name__ == "__main__":
    samples = [
        ("at://example/post/1", "Thanks for the thoughtful discussion everyone."),
        ("at://example/post/2", "That take is pretty rude, but I see your point."),
        ("at://example/post/3", "You are worthless garbage and should disappear."),
    ]
    for uri, text in samples:
        print(generate_feature(uri, text).model_dump())
