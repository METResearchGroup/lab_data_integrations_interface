"""LLM feature: classify political stance as left, right, neutral, or unclear.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/generate_features/political_stance/generate_feature.py
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ml_tooling.llm.llm import structured_chat_completion

SYSTEM_PROMPT = """\
You classify the political stance of short social media text into exactly one category:

- left: text aligned with left-wing or progressive US politics, such as support for \
expanded social programs, labor rights, climate regulation, gun control, or criticism \
typical of Democratic or progressive positions.
- right: text aligned with right-wing or conservative US politics, such as support for \
tax cuts, deregulation, strict immigration enforcement, gun rights, or criticism \
typical of Republican or conservative positions.
- neutral: text that is political but does not clearly lean left or right, such as \
nonpartisan factual reporting, balanced summaries, or procedural updates without \
advocacy.
- unclear: text where political stance cannot be determined, including non-political \
content, vague frustration about politics, or political content with mixed or \
insufficient partisan signals.

Use these examples:

Text: "We need Medicare for All and stronger unions, not more corporate tax breaks."
Political stance: left

Text: "Secure the border, cut wasteful spending, and stop government overreach."
Political stance: right

Text: "The Senate voted 52-48 to confirm the nominee."
Political stance: neutral

Text: "I'm so tired of politics right now."
Political stance: unclear

Text: "Republicans are blocking common-sense gun reform again."
Political stance: left

Text: "The Second Amendment protects law-abiding citizens, not criminals."
Political stance: right

Text: "City council meets Tuesday to discuss the zoning proposal."
Political stance: neutral

Text: "Just got coffee with an old friend. Good to catch up."
Political stance: unclear

Classify the user's text. Return only the structured fields requested.
"""


class LlmPoliticalStanceModel(BaseModel):
    political_stance: Literal["left", "right", "neutral", "unclear"] = Field(
        description="Political stance of the text: left, right, neutral, or unclear."
    )


def generate_feature(text: str) -> str:
    """Classify text as left, right, neutral, or unclear."""
    result = structured_chat_completion(
        user_prompt=text,
        output_schema=LlmPoliticalStanceModel,
        system_prompt=SYSTEM_PROMPT,
    )
    return result.political_stance


if __name__ == "__main__":
    samples = [
        "Expand Medicaid and fund public schools instead of another tax cut for billionaires.",
        "We need law and order, not defunding the police.",
        "The committee released its report on Tuesday.",
        "Great weather today.",
    ]
    for sample in samples:
        print(f"{sample!r} -> {generate_feature(sample)!r}")
