"""LLM feature: classify whether text is structurally complete.

Run from the repo root:

    PYTHONPATH=. uv run python \\
        data_platform/generate_features/is_structurally_complete/generate_feature.py
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ml_tooling.llm.llm import structured_chat_completion

SYSTEM_PROMPT = """\
Determine whether each social media post is complete or incomplete, using human-like \
understanding focused on structural signs, not tone or intent.

Label it structurally complete (True) if the post is not cut off and is not obviously \
part of a multi-post sequence.

Label it incomplete (False) only if:
- It contains unfinished sentences or appears cut off (e.g., "I am glad that you can \
come if you").
- It is explicitly part of a thread, such as being marked with numbering like [1/5], \
(2/3), or phrases like "to be continued."

A post can still be complete (True) even if it:
- Ends with a question.
- Invites replies, help, or opinions from others.
- Is vague, casual, informal, or grammatically imperfect.
- Expresses emotion, sarcasm, or surprise.
- Uses common social media abbreviations or slang.

Do not mark a post as incomplete just because it asks for input or sounds open-ended. \
Focus only on whether the text is truncated or clearly a fragment of a longer sequence.

Use these examples:

Text: "Congress passed the spending bill after a late-night vote."
Is structurally complete: True

Text: "I am glad that you can come if you"
Is structurally complete: False

Text: "Anyone know a good plumber in Austin?"
Is structurally complete: True

Text: "[1/5] A quick thread on why this bill matters."
Is structurally complete: False

Text: "lol what even is this"
Is structurally complete: True

Text: "(2/3) And then things got worse."
Is structurally complete: False

Text: "We need stronger gun laws!!!"
Is structurally complete: True

Text: "To be continued."
Is structurally complete: False

Classify the user's text. Return only the structured fields requested.
"""


class LlmIsStructurallyCompleteModel(BaseModel):
    is_structurally_complete: bool = Field(
        description=(
            "True if the post is structurally complete (not cut off, not an obvious "
            "thread fragment); False only for unfinished sentences or explicit thread "
            "markers."
        )
    )


class IsStructurallyCompleteModel(BaseModel):
    uri: str
    label_timestamp: str
    is_structurally_complete: bool


def generate_feature(uri: str, text: str) -> IsStructurallyCompleteModel:
    """Classify whether the post text is structurally complete."""
    from lib.timestamp_utils import get_current_timestamp

    result = structured_chat_completion(
        user_prompt=text,
        output_schema=LlmIsStructurallyCompleteModel,
        system_prompt=SYSTEM_PROMPT,
    )
    return IsStructurallyCompleteModel(
        uri=uri,
        label_timestamp=get_current_timestamp(),
        is_structurally_complete=result.is_structurally_complete,
    )


if __name__ == "__main__":
    samples = [
        ("at://example/post/1", "The Senate confirmed the nominee 52-48."),
        ("at://example/post/2", "[1/4] Here's why this ruling matters."),
        ("at://example/post/3", "thoughts on the new bill?"),
    ]
    for uri, text in samples:
        print(generate_feature(uri, text).model_dump())
