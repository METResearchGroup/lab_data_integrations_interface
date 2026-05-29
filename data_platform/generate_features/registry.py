from __future__ import annotations

from data_platform.generate_features.generate_features import FeatureSpec
from data_platform.generate_features.is_news_or_opinion.generate_feature import (
    IsNewsOrOpinionModel,
    generate_feature as generate_is_news_or_opinion,
)
from data_platform.generate_features.is_political.generate_feature import (
    IsPoliticalModel,
    generate_feature as generate_is_political,
)
from data_platform.generate_features.is_self_contained.generate_feature import (
    IsSelfContainedModel,
    generate_feature as generate_is_self_contained,
)
from data_platform.generate_features.is_structurally_complete.generate_feature import (
    IsStructurallyCompleteModel,
    generate_feature as generate_is_structurally_complete,
)
from data_platform.generate_features.is_toxic_tiered.generate_feature import (
    IsToxicTieredModel,
    generate_feature as generate_is_toxic_tiered,
)
from data_platform.generate_features.political_stance.generate_feature import (
    PoliticalStanceModel,
    generate_feature as generate_political_stance,
)

FEATURE_REGISTRY: dict[str, FeatureSpec] = {
    "is_news_or_opinion": FeatureSpec(
        name="is_news_or_opinion",
        generate_fn=generate_is_news_or_opinion,
        model=IsNewsOrOpinionModel,
    ),
    "is_political": FeatureSpec(
        name="is_political",
        generate_fn=generate_is_political,
        model=IsPoliticalModel,
    ),
    "is_self_contained": FeatureSpec(
        name="is_self_contained",
        generate_fn=generate_is_self_contained,
        model=IsSelfContainedModel,
    ),
    "is_structurally_complete": FeatureSpec(
        name="is_structurally_complete",
        generate_fn=generate_is_structurally_complete,
        model=IsStructurallyCompleteModel,
    ),
    "is_toxic_tiered": FeatureSpec(
        name="is_toxic_tiered",
        generate_fn=generate_is_toxic_tiered,
        model=IsToxicTieredModel,
    ),
    "political_stance": FeatureSpec(
        name="political_stance",
        generate_fn=generate_political_stance,
        model=PoliticalStanceModel,
    ),
}
