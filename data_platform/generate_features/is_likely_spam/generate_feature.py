"""LLM feature: classify whether text is likely spam.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/generate_features/is_likely_spam/generate_feature.py
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from lib.timestamp_utils import get_current_timestamp
from ml_tooling.llm.llm import structured_chat_completion

SYSTEM_PROMPT = """\
You classify whether short social media text is likely spam.

Label it spam (True) only when the text clearly tries to drive clicks, traffic, or
promotion in a way that is obviously spammy or link-farming.

Examples that should be True:
- Repeated promotional copy pushing a product, service, giveaway, or referral link.
- Posts whose main purpose is to send people to an external site for clicks.
- Obvious scammy, bot-like, or mass-marketing text.

Examples that should be False:
- Ordinary opinions, hot takes, complaints, or low-value commentary.
- Short or blunt text with no clear spam intent.
- News, discussion, jokes, or criticism even if they are repetitive or annoying.
- Posts that merely mention a website, brand, or external article without clear
  clickbait or promotional intent.

Be conservative. If the text is not clearly spam, return False.

Classify the user's text. Return only the structured fields requested.
"""


class LlmIsLikelySpamModel(BaseModel):
    is_likely_spam: bool = Field(
        description="True if the text is clearly spammy, promotional, or click-driving."
    )


class IsLikelySpamModel(BaseModel):
    uri: str
    label_timestamp: str
    is_likely_spam: bool


def generate_feature(uri: str, text: str) -> IsLikelySpamModel:
    """Classify whether the post text is likely spam."""
    result = structured_chat_completion(
        user_prompt=text,
        output_schema=LlmIsLikelySpamModel,
        system_prompt=SYSTEM_PROMPT,
    )
    return IsLikelySpamModel(
        uri=uri,
        label_timestamp=get_current_timestamp(),
        is_likely_spam=result.is_likely_spam,
    )


if __name__ == "__main__":
    samples = [
        ("at://example/post/1", "Check out our new product launch at example.com and click now!"),
        ("at://example/post/2", "I think this movie was overrated, honestly."),
        ("at://example/post/3", "Huge giveaway, limited time, visit scam-example.net to enter."),
    ]
    for uri, text in samples:
        print(generate_feature(uri, text).model_dump())
