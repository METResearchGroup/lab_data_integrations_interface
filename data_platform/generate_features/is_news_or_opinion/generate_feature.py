"""LLM feature: classify text as news, opinion, or neither.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/generate_features/is_news_or_opinion/generate_feature.py
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ml_tooling.llm.llm import structured_chat_completion

SYSTEM_PROMPT = """\
You classify short social media text into exactly one category:

- news: factual reporting or announcement of events, data, or developments. \
States what happened without advocating a personal viewpoint.
- opinion: commentary, analysis, or advocacy that expresses a personal or editorial \
viewpoint, judgment, or recommendation.
- neither: casual conversation, humor, questions, personal updates, or other content \
that is not news reporting or opinion commentary.

Use these examples:

Text: "The Federal Reserve raised interest rates by 25 basis points today."
Category: news

Text: "Inflation is finally cooling and that's great news for working families."
Category: opinion

Text: "Anyone else watching the game tonight?"
Category: neither

Text: "City council approved the new transit budget in a 7-2 vote."
Category: news

Text: "This policy is a disaster and lawmakers should be ashamed."
Category: opinion

Text: "Just got coffee with an old friend. Good to catch up."
Category: neither

Classify the user's text. Return only the structured fields requested.
"""


class LlmIsNewsOrOpinionModel(BaseModel):
    category: Literal["news", "opinion", "neither"] = Field(
        description="Whether the text is news reporting, opinion commentary, or neither."
    )


def generate_feature(text: str) -> str:
    """Classify text as news, opinion, or neither."""
    result = structured_chat_completion(
        user_prompt=text,
        output_schema=LlmIsNewsOrOpinionModel,
        system_prompt=SYSTEM_PROMPT,
    )
    return result.category


if __name__ == "__main__":
    samples = [
        "Breaking: wildfire evacuations ordered for three counties.",
        "We need stronger climate policy, not more empty promises.",
        "Happy Friday everyone!",
    ]
    for sample in samples:
        print(f"{sample!r} -> {generate_feature(sample)!r}")
