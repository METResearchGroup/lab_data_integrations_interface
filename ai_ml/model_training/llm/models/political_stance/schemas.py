from typing import Literal

from pydantic import BaseModel, Field

class LlmPoliticalStanceModel(BaseModel):
    political_stance: Literal["left", "right", "neutral", "unclear"] = Field(
        description="Political stance of the text: left, right, neutral, or unclear."
    )
