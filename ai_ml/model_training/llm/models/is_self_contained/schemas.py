from pydantic import BaseModel, Field

class LlmIsSelfContainedModel(BaseModel):
    is_self_contained: bool = Field(
        description=(
            "True if the post text alone is understandable with general US political "
            "knowledge; False if external context is needed."
        )
    )
