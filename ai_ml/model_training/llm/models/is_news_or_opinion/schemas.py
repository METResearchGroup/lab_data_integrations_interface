from typing import Literal

from pydantic import BaseModel, Field

class LlmIsNewsOrOpinionModel(BaseModel):
    category: Literal["news", "opinion", "neither"] = Field(
        description="Whether the text is news reporting, opinion commentary, or neither."
    )
