from pydantic import BaseModel, Field

class LlmIsPoliticalModel(BaseModel):
    is_political: bool = Field(
        description="True if the text is about politics, public policy, or civic affairs."
    )
