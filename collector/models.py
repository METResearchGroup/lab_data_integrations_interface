from pydantic import BaseModel


class GeneratedSocialMediaPost(BaseModel):
    text: str
    generation_timestamp: str


class LlmBatchedPosts(BaseModel):
    posts: list[str]
