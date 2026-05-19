from pydantic import BaseModel


class SocialMediaPost(BaseModel):
    id: str
    handle: str
    text: str
    post_timestamp: str


class LlmGeneratedSocialMediaPost(BaseModel):
    text: str


class GeneratedSocialMediaPost(BaseModel):
    text: str
    generation_timestamp: str


class LlmBatchedPosts(BaseModel):
    posts: list[str]
