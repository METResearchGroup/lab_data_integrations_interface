from __future__ import annotations

from data_platform.generate_features.is_likely_spam.generate_feature import (
    SYSTEM_PROMPT as IS_LIKELY_SPAM_SYSTEM_PROMPT,
)
from data_platform.generate_features.is_likely_spam.generate_feature import (
    IsLikelySpamModel,
    LlmIsLikelySpamModel,
)
from data_platform.generate_features.is_likely_spam.generate_feature import (
    generate_feature as generate_is_likely_spam,
)
from data_platform.generate_features.is_news_or_opinion.generate_feature import (
    SYSTEM_PROMPT as IS_NEWS_OR_OPINION_SYSTEM_PROMPT,
)
from data_platform.generate_features.is_news_or_opinion.generate_feature import (
    IsNewsOrOpinionModel,
    LlmIsNewsOrOpinionModel,
)
from data_platform.generate_features.is_news_or_opinion.generate_feature import (
    generate_feature as generate_is_news_or_opinion,
)
from data_platform.generate_features.is_political.generate_feature import (
    SYSTEM_PROMPT as IS_POLITICAL_SYSTEM_PROMPT,
)
from data_platform.generate_features.is_political.generate_feature import (
    IsPoliticalModel,
    LlmIsPoliticalModel,
)
from data_platform.generate_features.is_political.generate_feature import (
    generate_feature as generate_is_political,
)
from data_platform.generate_features.is_self_contained.generate_feature import (
    SYSTEM_PROMPT as IS_SELF_CONTAINED_SYSTEM_PROMPT,
)
from data_platform.generate_features.is_self_contained.generate_feature import (
    IsSelfContainedModel,
    LlmIsSelfContainedModel,
)
from data_platform.generate_features.is_self_contained.generate_feature import (
    generate_feature as generate_is_self_contained,
)
from data_platform.generate_features.is_structurally_complete.generate_feature import (
    SYSTEM_PROMPT as IS_STRUCTURALLY_COMPLETE_SYSTEM_PROMPT,
)
from data_platform.generate_features.is_structurally_complete.generate_feature import (
    IsStructurallyCompleteModel,
    LlmIsStructurallyCompleteModel,
)
from data_platform.generate_features.is_structurally_complete.generate_feature import (
    generate_feature as generate_is_structurally_complete,
)
from data_platform.generate_features.is_toxic_tiered.generate_feature import IsToxicTieredModel
from data_platform.generate_features.is_toxic_tiered.generate_feature import (
    generate_feature as generate_is_toxic_tiered,
)
from data_platform.generate_features.is_toxic_tiered_v2.generate_feature import (
    IsToxicTieredV2Model,
)
from data_platform.generate_features.is_toxic_tiered_v2.generate_feature import (
    generate_feature as generate_is_toxic_tiered_v2,
)
from data_platform.generate_features.models import FeatureSpec
from data_platform.generate_features.political_stance.generate_feature import (
    SYSTEM_PROMPT as POLITICAL_STANCE_SYSTEM_PROMPT,
)
from data_platform.generate_features.political_stance.generate_feature import (
    LlmPoliticalStanceModel,
    PoliticalStanceModel,
)
from data_platform.generate_features.political_stance.generate_feature import (
    generate_feature as generate_political_stance,
)

FEATURE_REGISTRY: dict[str, FeatureSpec] = {
    "is_news_or_opinion": FeatureSpec(
        name="is_news_or_opinion",
        model=IsNewsOrOpinionModel,
        engine_type="langchain",
        generate_fn=generate_is_news_or_opinion,
        system_prompt=IS_NEWS_OR_OPINION_SYSTEM_PROMPT,
        llm_output_schema=LlmIsNewsOrOpinionModel,
    ),
    "is_political": FeatureSpec(
        name="is_political",
        model=IsPoliticalModel,
        engine_type="langchain",
        generate_fn=generate_is_political,
        system_prompt=IS_POLITICAL_SYSTEM_PROMPT,
        llm_output_schema=LlmIsPoliticalModel,
    ),
    "is_likely_spam": FeatureSpec(
        name="is_likely_spam",
        model=IsLikelySpamModel,
        engine_type="langchain",
        generate_fn=generate_is_likely_spam,
        system_prompt=IS_LIKELY_SPAM_SYSTEM_PROMPT,
        llm_output_schema=LlmIsLikelySpamModel,
    ),
    "is_self_contained": FeatureSpec(
        name="is_self_contained",
        model=IsSelfContainedModel,
        engine_type="langchain",
        generate_fn=generate_is_self_contained,
        system_prompt=IS_SELF_CONTAINED_SYSTEM_PROMPT,
        llm_output_schema=LlmIsSelfContainedModel,
    ),
    "is_structurally_complete": FeatureSpec(
        name="is_structurally_complete",
        model=IsStructurallyCompleteModel,
        engine_type="langchain",
        generate_fn=generate_is_structurally_complete,
        system_prompt=IS_STRUCTURALLY_COMPLETE_SYSTEM_PROMPT,
        llm_output_schema=LlmIsStructurallyCompleteModel,
    ),
    "is_toxic_tiered": FeatureSpec(
        name="is_toxic_tiered",
        model=IsToxicTieredModel,
        engine_type="thread_pool",
        generate_fn=generate_is_toxic_tiered,
    ),
    "is_toxic_tiered_v2": FeatureSpec(
        name="is_toxic_tiered_v2",
        model=IsToxicTieredV2Model,
        engine_type="thread_pool",
        generate_fn=generate_is_toxic_tiered_v2,
    ),
    "political_stance": FeatureSpec(
        name="political_stance",
        model=PoliticalStanceModel,
        engine_type="langchain",
        generate_fn=generate_political_stance,
        system_prompt=POLITICAL_STANCE_SYSTEM_PROMPT,
        llm_output_schema=LlmPoliticalStanceModel,
    ),
}

OPT_IN_FEATURE_NAMES = frozenset({"is_toxic_tiered_v2"})


def default_feature_registry() -> dict[str, FeatureSpec]:
    return {k: v for k, v in FEATURE_REGISTRY.items() if k not in OPT_IN_FEATURE_NAMES}
