from pydantic import BaseModel, Field


class PerspectiveApiLabelsModel(BaseModel):
    """Stores results of classifications from Perspective API.

    Uses all the available attributes from the Perspective API, so that we have
    this data in the future as well for exploratory analysis.
    """

    uri: str = Field(..., description="The URI of the post.")
    text: str = Field(..., description="The text of the post.")
    preprocessing_timestamp: str = Field(
        ..., description="The preprocessing_timestamp timestamp of the post."
    )
    was_successfully_labeled: bool = Field(
        ...,
        description="Indicates if the post was successfully labeled by the Perspective API.",
    )  # noqa
    reason: str | None = Field(
        default=None,
        description="Reason for why the post was not labeled successfully.",
    )  # noqa
    label_timestamp: str = Field(
        ...,
        description=(
            "Timestamp when the post was labeled (or, if labeling failed, when it was attempted)."
        ),
    )
    prob_toxic: float | None = Field(default=None, description="Probability of toxicity.")
    prob_severe_toxic: float | None = Field(
        default=None, description="Probability of severe toxicity."
    )
    prob_identity_attack: float | None = Field(
        default=None, description="Probability of identity attack."
    )
    prob_insult: float | None = Field(default=None, description="Probability of insult.")
    prob_profanity: float | None = Field(default=None, description="Probability of profanity.")
    prob_threat: float | None = Field(default=None, description="Probability of threat.")
    prob_affinity: float | None = Field(default=None, description="Probability of affinity.")
    prob_compassion: float | None = Field(default=None, description="Probability of compassion.")
    prob_constructive: float | None = Field(
        default=None, description="Probability of constructive."
    )
    prob_curiosity: float | None = Field(default=None, description="Probability of curiosity.")
    prob_nuance: float | None = Field(default=None, description="Probability of nuance.")
    prob_personal_story: float | None = Field(
        default=None, description="Probability of personal story."
    )
    prob_reasoning: float | None = Field(default=None, description="Probability of reasoning.")
    prob_respect: float | None = Field(default=None, description="Probability of respect.")
    prob_alienation: float | None = Field(default=None, description="Probability of alienation.")
    prob_fearmongering: float | None = Field(
        default=None, description="Probability of fearmongering."
    )
    prob_generalization: float | None = Field(
        default=None, description="Probability of generalization."
    )
    prob_moral_outrage: float | None = Field(
        default=None, description="Probability of moral outrage."
    )
    prob_scapegoating: float | None = Field(
        default=None, description="Probability of scapegoating."
    )
    prob_sexually_explicit: float | None = Field(
        default=None, description="Probability of sexually explicit."
    )
    prob_flirtation: float | None = Field(default=None, description="Probability of flirtation.")
    prob_spam: float | None = Field(default=None, description="Probability of spam.")
