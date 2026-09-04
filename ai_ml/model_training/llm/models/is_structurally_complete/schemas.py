from pydantic import BaseModel, Field

class LlmIsStructurallyCompleteModel(BaseModel):
    is_structurally_complete: bool = Field(
        description=(
            "True if the post is structurally complete (not cut off, not an obvious "
            "thread fragment); False only for unfinished sentences or explicit thread "
            "markers."
        )
    )
