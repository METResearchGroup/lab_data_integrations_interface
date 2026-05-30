"""LLM feature: classify whether text is self-contained.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/generate_features/is_self_contained/generate_feature.py
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ml_tooling.llm.llm import structured_chat_completion

SYSTEM_PROMPT = """\
Classify whether a social media post is self-contained or not, based on general and \
common US political knowledge.

Label it self-contained (True) if the pure text of the post (without links, media, \
images, or thread context) can be understood by people with general and common US \
political knowledge. Examples include references to mass shootings, school shootings, \
or which party (left or right) usually mentions them.

Label it not self-contained (False) if the pure text of the post (without links, media, \
images, or thread context) cannot be understood by people with general and common US \
political knowledge, and such people would need to read specific news, links, videos, \
or social media threads to understand the post. Examples include what type of gun a \
shooter used in a specific shooting event, or what the shooter's grandmother said.

Use these examples:

Text: "After every school shooting, Republicans talk about mental health while Democrats \
push for gun control."
Is self-contained: True

Text: "He used a modified Sig Sauer with a bump stock."
Is self-contained: False

Text: "Mass shootings keep happening and Congress still does nothing."
Is self-contained: True

Text: "She told reporters he had been acting strange since he lost his job at the plant."
Is self-contained: False

Text: "The right always deflects after mass shootings instead of addressing guns."
Is self-contained: True

Text: "The suspect's grandmother said he stopped taking his medication in March."
Is self-contained: False

Classify the user's text. Return only the structured fields requested.
"""


class LlmIsSelfContainedModel(BaseModel):
    is_self_contained: bool = Field(
        description=(
            "True if the post text alone is understandable with general US political "
            "knowledge; False if external context is needed."
        )
    )


class IsSelfContainedModel(BaseModel):
    uri: str
    is_self_contained: bool


def generate_feature(uri: str, text: str) -> IsSelfContainedModel:
    """Classify whether the post text is self-contained."""
    result = structured_chat_completion(
        user_prompt=text,
        output_schema=LlmIsSelfContainedModel,
        system_prompt=SYSTEM_PROMPT,
    )
    return IsSelfContainedModel(uri=uri, is_self_contained=result.is_self_contained)


if __name__ == "__main__":
    samples = [
        (
            "at://example/post/1",
            ("Republicans always bring up mental health after school shootings."),
        ),
        ("at://example/post/2", "He bought the rifle legally at a gun show last year."),
        ("at://example/post/3", "The left wants background checks expanded nationwide."),
    ]
    for uri, text in samples:
        print(generate_feature(uri, text).model_dump())
