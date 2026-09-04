from pydantic import BaseModel, Field

class LlmIsLikelySpamModel(BaseModel):
    is_likely_spam: bool = Field(
        description="True if the text is clearly spammy, promotional, or click-driving."
    )
