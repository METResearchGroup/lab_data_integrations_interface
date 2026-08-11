from typing import Optional

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
    reason: Optional[str] = Field(
        default=None,
        description="Reason for why the post was not labeled successfully.",
    )  # noqa
    label_timestamp: str = Field(
        ...,
        description="Timestamp when the post was labeled (or, if labeling failed, when it was attempted).",
    )  # noqa
    prob_toxic: Optional[float] = Field(
        default=None, description="Probability of toxicity."
    )
    prob_severe_toxic: Optional[float] = Field(
        default=None, description="Probability of severe toxicity."
    )
    prob_identity_attack: Optional[float] = Field(
        default=None, description="Probability of identity attack."
    )
    prob_insult: Optional[float] = Field(
        default=None, description="Probability of insult."
    )
    prob_profanity: Optional[float] = Field(
        default=None, description="Probability of profanity."
    )
    prob_threat: Optional[float] = Field(
        default=None, description="Probability of threat."
    )
    prob_affinity: Optional[float] = Field(
        default=None, description="Probability of affinity."
    )
    prob_compassion: Optional[float] = Field(
        default=None, description="Probability of compassion."
    )
    prob_constructive: Optional[float] = Field(
        default=None, description="Probability of constructive."
    )
    prob_curiosity: Optional[float] = Field(
        default=None, description="Probability of curiosity."
    )
    prob_nuance: Optional[float] = Field(
        default=None, description="Probability of nuance."
    )
    prob_personal_story: Optional[float] = Field(
        default=None, description="Probability of personal story."
    )
    prob_reasoning: Optional[float] = Field(
        default=None, description="Probability of reasoning."
    )
    prob_respect: Optional[float] = Field(
        default=None, description="Probability of respect."
    )
    prob_alienation: Optional[float] = Field(
        default=None, description="Probability of alienation."
    )
    prob_fearmongering: Optional[float] = Field(
        default=None, description="Probability of fearmongering."
    )
    prob_generalization: Optional[float] = Field(
        default=None, description="Probability of generalization."
    )
    prob_moral_outrage: Optional[float] = Field(
        default=None, description="Probability of moral outrage."
    )
    prob_scapegoating: Optional[float] = Field(
        default=None, description="Probability of scapegoating."
    )
    prob_sexually_explicit: Optional[float] = Field(
        default=None, description="Probability of sexually explicit."
    )
    prob_flirtation: Optional[float] = Field(
        default=None, description="Probability of flirtation."
    )
    prob_spam: Optional[float] = Field(default=None, description="Probability of spam.")
