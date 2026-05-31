"""LLM feature: classify whether text is political.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/generate_features/is_political/generate_feature.py
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ml_tooling.llm.llm import structured_chat_completion

SYSTEM_PROMPT = """\
You classify whether short social media text is political.

Label it political (True) if the text is about government, elections, public policy, \
political parties, legislation, political figures, geopolitics, or civic issues where \
the content is clearly tied to public affairs or partisan debate.

Label it not political (False) if the text is about personal life, entertainment, \
sports, hobbies, consumer products, or other topics with no meaningful connection to \
government or public policy.

Use these examples:

Text: "Republicans blocked the infrastructure bill again."
Is political: True

Text: "My dog learned a new trick today."
Is political: False

Text: "The Senate confirmed the nominee 52-48."
Is political: True

Text: "Anyone have restaurant recs downtown?"
Is political: False

Text: "We need Medicare for All, not another corporate giveaway."
Is political: True

Text: "Just finished the season finale and I'm still crying."
Is political: False

Classify the user's text. Return only the structured fields requested.
"""


class LlmIsPoliticalModel(BaseModel):
    is_political: bool = Field(
        description="True if the text is about politics, public policy, or civic affairs."
    )


class IsPoliticalModel(BaseModel):
    uri: str
    label_timestamp: str
    is_political: bool


def generate_feature(uri: str, text: str) -> IsPoliticalModel:
    """Classify whether the post text is political."""
    from lib.timestamp_utils import get_current_timestamp

    result = structured_chat_completion(
        user_prompt=text,
        output_schema=LlmIsPoliticalModel,
        system_prompt=SYSTEM_PROMPT,
    )
    return IsPoliticalModel(
        uri=uri,
        label_timestamp=get_current_timestamp(),
        is_political=result.is_political,
    )


if __name__ == "__main__":
    samples = [
        ("at://example/post/1", "Congress passed the spending bill after a late-night vote."),
        ("at://example/post/2", "Best pizza in Chicago? Go."),
        ("at://example/post/3", "Democrats are pushing for another round of stimulus checks."),
    ]
    for uri, text in samples:
        print(generate_feature(uri, text).model_dump())
